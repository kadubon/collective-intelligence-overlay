"""One owner's PostgreSQL store. Migrations are explicit, records append-only."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    and_,
    create_engine,
    func,
    insert,
    literal,
    or_,
    select,
    update,
)
from sqlalchemy import (
    event as sql_event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from .models import (
    Capability,
    Decision,
    Event,
    Evidence,
    Record,
    RecordRef,
    Revocation,
    Subject,
    UseRequest,
    now,
    uid,
)
from .pg8000_compat import ManagedConnection
from .queries import RecordCursor, RecordPage, RecordQuery
from .security import Principal, verify

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("kind", String(32), primary_key=True),
    Column("issuer", String(160), primary_key=True),
    Column("record_id", String(330), primary_key=True),
    Column("body", JSON, nullable=False),
    Column("envelope", JSON, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("subject_key", String(64)),
    Column("subject_id", String(160)),
    Column("subject_version", String(160)),
    Column("subject_digest", String(64)),
    Column("claim", String(160)),
    Column("evidence_id", String(160)),
    Column("scope_digest", String(64)),
    Column("receivers", JSONB),
    Column("task_id", String(160)),
    Column("attempt_id", String(160)),
    Column("occurred_at", DateTime(timezone=True)),
    Column("policy_digest", String(64)),
    Column("dependency_refs", JSONB),
)
feed_state = Table(
    "feed_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("generation", String(64), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("restore_pending", Boolean, nullable=False, server_default="false"),
    Column("restored_at", DateTime(timezone=True)),
    Column("recovery_receipt", String(160)),
    Column("recovery_digest", String(64)),
)
subject_revisions = Table(
    "subject_revisions",
    metadata,
    Column("subject_key", String(64), primary_key=True),
    Column("revision", BigInteger, nullable=False),
)


def projection_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def subject_key(subject: Subject) -> str:
    return projection_digest([subject.id, subject.version, subject.digest])


decisions = Table(
    "decisions",
    metadata,
    Column("id", String(160), primary_key=True),
    Column("body", JSON, nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("subject_key", String(64), nullable=False),
    Column("scope_digest", String(64), nullable=False),
    Column("policy_digest", String(64), nullable=False),
    Column("evaluated_at", DateTime(timezone=True), nullable=False),
)
leases = Table(
    "leases",
    metadata,
    Column("task_id", String(160), primary_key=True),
    Column("worker", String(160), nullable=False),
    Column("fence", Integer, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("state", String(16), nullable=False),
    Column("reservation", Numeric(24, 9), nullable=False),
    Column("unit", String(160), nullable=False),
    Column("actual", Numeric(24, 9), nullable=True),
)
budgets = Table(
    "budgets",
    metadata,
    Column("unit", String(160), primary_key=True),
    Column("remaining", Numeric(24, 9), nullable=False),
)
dependencies = Table(
    "dependencies",
    metadata,
    Column("parent", String(330), primary_key=True),
    Column("child", String(330), primary_key=True),
    Column("digest", String(64), nullable=False),
)


class Conflict(ValueError):
    """Same record identity with different content, or stale execution ownership."""


@dataclass(frozen=True)
class AdmissionSnapshot:
    capabilities: list[Capability]
    evidence: list[Evidence]
    revocations: list[Revocation]
    revisions: dict[str, int]


class Store:
    def __init__(self, url: str, owner: str, principals: dict[str, Principal]) -> None:
        if not url.startswith("postgresql+pg8000://"):
            raise ValueError("reference storage requires PostgreSQL with pg8000")
        self.owner = owner
        self.principals = dict(principals)
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"timeout": 5},
            pool_size=4,
            max_overflow=0,
            pool_timeout=5,
        )

        @sql_event.listens_for(self.engine, "do_connect")
        def connect(dialect: Any, record: Any, arguments: Any, parameters: Any) -> Any:
            return ManagedConnection(*arguments, **parameters)

        @sql_event.listens_for(self.engine, "connect")
        def set_timeouts(connection: Any, _: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("SET statement_timeout = '5s'")
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET idle_in_transaction_session_timeout = '10s'")
            cursor.close()
            connection.commit()

        # SQLAlchemy's public cursor events measure execution, excluding pool
        # acquisition, connection establishment and transaction commit. Never
        # put SQL, parameters, exceptions or connection URLs in the observation.
        @sql_event.listens_for(self.engine, "before_cursor_execute")
        def cursor_started(
            conn: Connection, cursor: Any, statement: Any, parameters: Any, context: Any, many: Any
        ) -> None:
            conn.info["cio_cursor_observation"] = (context, time.perf_counter())

        def cursor_finished(conn: Connection, context: Any, failed: bool) -> None:
            observed = conn.info.pop("cio_cursor_observation", None)
            if observed is None or observed[0] is not context:
                return
            logging.getLogger(__name__).info(
                json.dumps(
                    {
                        "owner": self.owner,
                        "reason": "DATABASE_CURSOR_FAILED"
                        if failed
                        else "DATABASE_CURSOR_FINISHED",
                        "elapsed_seconds": time.perf_counter() - observed[1],
                    }
                )
            )

        @sql_event.listens_for(self.engine, "after_cursor_execute")
        def cursor_returned(
            conn: Connection, cursor: Any, statement: Any, parameters: Any, context: Any, many: Any
        ) -> None:
            cursor_finished(conn, context, False)

        @sql_event.listens_for(self.engine, "handle_error")
        def cursor_failed(context: Any) -> None:
            if context.connection is not None and context.execution_context is not None:
                cursor_finished(context.connection, context.execution_context, True)

    def close(self) -> None:
        self.engine.dispose()

    def put(self, envelope: dict[str, Any]) -> bool:
        record = verify(envelope, self.principals)
        with self.engine.begin() as conn:
            return self._insert(conn, record, envelope)

    @staticmethod
    def _insert(conn: Connection, record: Record, envelope: dict[str, Any]) -> bool:
        key = record.subject.key if isinstance(record, Capability) else record.id
        # The authenticated payload remains the source of truth. Do not rewrite
        # v1 data by serializing the current model's new defaults into it.
        body = json.loads(base64.b64decode(envelope["payload"]))
        selector = (
            (records.c.kind == record.kind)
            & (records.c.issuer == record.issuer)
            & (records.c.record_id == key)
        )
        # All publishers lock the same row *before* allocating a sequence. This
        # lock is retained through commit, so no later committed prefix can skip
        # a smaller sequence from an uncommitted transaction. Rollback restores it.
        prefix: int = conn.execute(
            select(feed_state.c.sequence).where(feed_state.c.id == 1).with_for_update()
        ).scalar_one()
        subject = record.subject
        skey = subject_key(subject)
        receipt = body.get("execution") or body.get("formation") or body.get("work") or {}
        scope = body.get("scope") or receipt.get("scope")
        result = conn.execute(
            pg_insert(records)
            .values(
                kind=record.kind,
                issuer=record.issuer,
                record_id=key,
                body=body,
                envelope=envelope,
                received_at=now(),
                sequence=prefix + 1,
                subject_key=skey,
                subject_id=subject.id,
                subject_version=subject.version,
                subject_digest=subject.digest,
                claim=body.get("claim"),
                evidence_id=body.get("evidence_id"),
                scope_digest=projection_digest(scope) if scope else None,
                receivers=body.get("receivers", []),
                task_id=body.get("task_id"),
                attempt_id=body.get("attempt_id"),
                occurred_at=record.occurred_at if isinstance(record, Event) else record.created_at,
                policy_digest=body.get("policy_digest") or receipt.get("policy_digest"),
                dependency_refs=[
                    {
                        "subject_key": subject_key(dep),
                        "issuer": record.dependency_issuers[index]
                        if record.dependency_issuers
                        else None,
                    }
                    for index, dep in enumerate(record.dependencies)
                ]
                if isinstance(record, Capability)
                else [],
            )
            .on_conflict_do_nothing()
        )
        if result.rowcount == 0:
            old: Any = conn.execute(select(records.c.body).where(selector)).scalar_one()
            if old != body:
                raise Conflict("record identity conflict")
            return False
        conn.execute(update(feed_state).where(feed_state.c.id == 1).values(sequence=prefix + 1))
        affected = {skey} if isinstance(record, Capability | Evidence | Revocation) else set()
        if isinstance(record, Revocation) and record.evidence_id is not None:
            affected.update(
                conn.execute(
                    select(records.c.subject_key).where(
                        (records.c.kind == "evidence")
                        & (records.c.issuer == record.issuer)
                        & (records.c.record_id == record.evidence_id)
                    )
                ).scalars()
            )
        for affected_key in affected:
            conn.execute(
                pg_insert(subject_revisions)
                .values(subject_key=affected_key, revision=1)
                .on_conflict_do_update(
                    index_elements=["subject_key"],
                    set_={"revision": subject_revisions.c.revision + 1},
                )
            )
        if isinstance(record, Capability):
            for dep in record.dependencies:
                conn.execute(
                    insert(dependencies).values(
                        parent=record.issuer + "/" + key, child=dep.key, digest=dep.digest
                    )
                )
        return True

    def commit_work(
        self,
        task_id: str,
        worker: str,
        fence: int,
        envelopes: list[dict[str, Any]],
        *,
        cancelled: bool = False,
    ) -> None:
        validated = [(verify(e, self.principals), e) for e in envelopes]
        with self.engine.begin() as conn:
            row = (
                conn.execute(select(leases).where(leases.c.task_id == task_id).with_for_update())
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["worker"] != worker
                or row["fence"] != fence
                or row["state"] != "active"
                or row["expires_at"] <= now()
            ):
                raise Conflict("stale worker cannot commit results")
            for record, envelope in validated:
                if record.issuer != self.owner:
                    raise ValueError("work can only emit own records")
                self._insert(conn, record, envelope)
            conn.execute(
                update(leases)
                .where(leases.c.task_id == task_id)
                .values(
                    state="cancelled" if cancelled else "complete",
                    actual=None,  # reservation is not measured consumption
                )
            )

    def record_count(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(records)).scalar_one())

    def resolve_reference(self, reference: RecordRef) -> Record | Decision:
        """Resolve one exact observation, never infer permission from its existence.

        Signed record digests cover original DSSE payload bytes, including legacy
        representations. Local decisions use the existing projection digest and
        cannot be attributed to another owner. No history scan or fallback occurs.
        """
        with self.engine.connect() as conn:
            if reference.kind == "decision":
                if reference.issuer != self.owner:
                    raise ValueError("decision reference belongs to another owner")
                body = conn.execute(
                    select(decisions.c.body).where(decisions.c.id == reference.id)
                ).scalar_one_or_none()
                if body is None or projection_digest(body) != reference.payload_digest:
                    raise ValueError("missing or mismatched decision reference")
                return Decision.model_validate(body)
            envelope = conn.execute(
                select(records.c.envelope).where(
                    (records.c.kind == reference.kind)
                    & (records.c.issuer == reference.issuer)
                    & (records.c.record_id == reference.id)
                )
            ).scalar_one_or_none()
        if envelope is None:
            raise ValueError("missing record reference")
        payload = base64.b64decode(envelope["payload"], validate=True)
        if hashlib.sha256(payload).hexdigest() != reference.payload_digest:
            raise ValueError("mismatched record reference")
        return verify(envelope, self.principals, require_authority=False)

    def reference(self, kind: str, issuer: str, record_id: str) -> RecordRef:
        """Get an exact reference from stored bytes, not current model defaults."""
        # Validate the selector before touching the store.
        reference = RecordRef(kind=kind, issuer=issuer, id=record_id, payload_digest="0" * 64)  # type: ignore[arg-type]
        with self.engine.connect() as conn:
            if reference.kind == "decision":
                if issuer != self.owner:
                    raise ValueError("decision reference belongs to another owner")
                body = conn.execute(
                    select(decisions.c.body).where(decisions.c.id == record_id)
                ).scalar_one_or_none()
                if body is None:
                    raise ValueError("missing decision reference")
                value = projection_digest(body)
            else:
                envelope = conn.execute(
                    select(records.c.envelope).where(
                        (records.c.kind == kind)
                        & (records.c.issuer == issuer)
                        & (records.c.record_id == record_id)
                    )
                ).scalar_one_or_none()
                if envelope is None:
                    raise ValueError("missing record reference")
                verify(envelope, self.principals, require_authority=False)
                value = hashlib.sha256(
                    base64.b64decode(envelope["payload"], validate=True)
                ).hexdigest()
        return reference.model_copy(update={"payload_digest": value})

    def signed_record(self, reference: RecordRef) -> dict[str, Any]:
        """Return original authenticated bytes for an exact, already-authorized export."""
        if reference.kind == "decision":
            raise ValueError("local decisions cannot be exported as signed records")
        with self.engine.connect() as conn:
            envelope = conn.execute(
                select(records.c.envelope).where(
                    (records.c.kind == reference.kind)
                    & (records.c.issuer == reference.issuer)
                    & (records.c.record_id == reference.id)
                )
            ).scalar_one_or_none()
        if (
            envelope is None
            or hashlib.sha256(base64.b64decode(envelope["payload"], validate=True)).hexdigest()
            != reference.payload_digest
        ):
            raise ValueError("missing or mismatched signed record")
        verify(envelope, self.principals, require_authority=False)
        return dict(envelope)

    def reset_sync_after_restore(self) -> str:
        """Offline operator recovery: rotate feed generation and discard freshness.

        Stop all writers/peers before this operation. This cannot reconstruct work
        or withdrawals absent from the backup; reconcile them before resuming use.
        Signed records, reservations, leases and invocation results are preserved.
        """
        from .synchronization import checkpoints

        generation = uid()
        with self.engine.begin() as conn:
            conn.execute(select(feed_state).where(feed_state.c.id == 1).with_for_update()).one()
            conn.execute(
                update(feed_state)
                .where(feed_state.c.id == 1)
                .values(
                    generation=generation,
                    restore_pending=True,
                    restored_at=func.clock_timestamp(),
                    recovery_receipt=None,
                    recovery_digest=None,
                )
            )
            conn.execute(
                update(checkpoints).values(
                    generation=None,
                    through=0,
                    upper=0,
                    anchor=None,
                    cursor=None,
                    complete=False,
                    last_receipt=None,
                    completed_at=None,
                )
            )
            conn.execute(
                update(subject_revisions).values(revision=subject_revisions.c.revision + 1)
            )
        return generation

    def restore_pending(self) -> bool:
        with self.engine.connect() as conn:
            return bool(
                conn.execute(
                    select(feed_state.c.restore_pending).where(feed_state.c.id == 1)
                ).scalar_one()
            )

    @staticmethod
    def _revisions(conn: Connection, keys: set[str]) -> dict[str, int]:
        result = dict.fromkeys(keys, 0)
        if keys:
            for key, revision in conn.execute(
                select(subject_revisions).where(subject_revisions.c.subject_key.in_(keys))
            ):
                result[str(key)] = int(revision)  # type: ignore[call-overload]
        return result

    def revisions(self, keys: set[str]) -> dict[str, int]:
        if len(keys) > 2048:
            raise ValueError("revision check exceeds dependency bound")
        with self.engine.connect() as conn:
            return self._revisions(conn, keys)

    def admission_snapshot(self, request: UseRequest, max_nodes: int) -> AdmissionSnapshot:
        """Bounded indexed closure in one repeatable-read snapshot.

        Neither unrelated events nor unrelated subjects are loaded or verified.
        Exceeding related evidence bounds fails closed; no partial PASS subset is used.
        """
        caps: list[Capability] = []
        evidence: list[Evidence] = []
        revocations: list[Revocation] = []
        seen: set[str] = set()
        visited: set[tuple[str, str | None]] = set()
        frontier = {(subject_key(request.subject), request.capability_issuer)}
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            with conn.begin():

                def fetch(condition: Any, limit: int) -> list[Record]:
                    rows: Any = (
                        conn.execute(select(records.c.envelope).where(condition).limit(limit + 1))
                        .scalars()
                        .all()
                    )
                    if len(rows) > limit:
                        raise ValueError("related record safety bound exceeded")
                    return [verify(row, self.principals) for row in rows]

                while frontier:
                    if len(visited | frontier) > max_nodes:
                        raise ValueError("dependency closure safety bound exceeded")
                    found = fetch(
                        (records.c.kind == "capability")
                        & or_(
                            *(
                                and_(
                                    records.c.subject_key == key,
                                    records.c.issuer == issuer,
                                )
                                if issuer is not None
                                else records.c.subject_key == key
                                for key, issuer in frontier
                            )
                        ),
                        max_nodes * 2,
                    )
                    batch = [record for record in found if isinstance(record, Capability)]
                    caps.extend(batch)
                    visited.update(frontier)
                    seen.update(key for key, _ in frontier)
                    frontier = (
                        {
                            (
                                subject_key(dep),
                                cap.dependency_issuers[index] if cap.dependency_issuers else None,
                            )
                            for cap in batch
                            for index, dep in enumerate(cap.dependencies)
                        }
                        | {
                            (subject_key(item.subject), item.issuer)
                            for cap in batch
                            for item in cap.formation_inputs
                        }
                    ) - visited

                # Scope/claim/receiver filtering happens in SQL, including the root
                # requested scope (which can differ from the capability's scope).
                predicates = []
                for cap in caps:
                    scope = request.scope if cap.subject == request.subject else cap.scope
                    predicates.append(
                        and_(
                            records.c.subject_key == subject_key(cap.subject),
                            records.c.scope_digest
                            == projection_digest(scope.model_dump(mode="json")),
                            records.c.claim == cap.claim,
                        )
                    )
                if predicates:
                    found = fetch(
                        and_(
                            records.c.kind == "evidence",
                            or_(*predicates),
                            records.c.receivers.contains([request.receiver]),
                        ),
                        2048,
                    )
                    evidence = [record for record in found if isinstance(record, Evidence)]
                # Legacy evidence references lack issuer: keep all collisions so
                # qualification rejects ambiguity, never pick the first row.
                loaded_ids = {e.id for e in evidence}
                pending = {eid for e in evidence for eid in e.evidence_dependencies} - loaded_ids
                while pending:
                    if len(evidence) + len(pending) > 2048:
                        raise ValueError("evidence closure safety bound exceeded")
                    found = fetch(
                        (records.c.kind == "evidence") & records.c.record_id.in_(pending),
                        2048 - len(evidence),
                    )
                    support = [record for record in found if isinstance(record, Evidence)]
                    evidence.extend(support)
                    loaded_ids.update(pending)
                    pending = {eid for e in support for eid in e.evidence_dependencies} - loaded_ids
                seen.update(subject_key(e.subject) for e in evidence)
                if len(seen) > 2048:
                    raise ValueError("related subject safety bound exceeded")
                found = fetch(
                    (records.c.kind == "revocation")
                    & or_(
                        records.c.subject_key.in_(seen),
                        records.c.evidence_id.in_(loaded_ids),
                    ),
                    2048,
                )
                revocations = [record for record in found if isinstance(record, Revocation)]
                revisions = self._revisions(conn, seen)
        return AdmissionSnapshot(caps, evidence, revocations, revisions)

    def record_page(
        self,
        query: RecordQuery,
        *,
        cursor: RecordCursor | None = None,
        limit: int = 128,
        byte_limit: int = 196608,
    ) -> RecordPage:
        """Verified records in a stable committed prefix; no OFFSET or silent truncation.

        Local cursors are inspectable state, not signed authorization. The caller
        must already have owner-level inspection access. Use Feed for peer sharing.
        """
        if not 1 <= limit <= 256 or not 1024 <= byte_limit <= 1048576:
            raise ValueError("invalid inspection page bound")
        query_digest = projection_digest(query.model_dump(mode="json"))
        local_decisions = query.kinds == ("decision",)
        table = decisions if local_decisions else records
        with self.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            with conn.begin():
                state = conn.execute(select(feed_state)).mappings().one()
                if cursor is None:
                    cursor = RecordCursor(
                        owner=self.owner,
                        generation=state["generation"],
                        query_digest=query_digest,
                        anchor=now(),
                        after=0,
                        upper=state["sequence"],
                    )
                elif (
                    cursor.owner != self.owner
                    or cursor.generation != state["generation"]
                    or cursor.query_digest != query_digest
                    or cursor.upper > state["sequence"]
                ):
                    raise ValueError(
                        "inspection cursor owner, filter or restored generation mismatch"
                    )
                condition = (table.c.sequence > cursor.after) & (table.c.sequence <= cursor.upper)
                if not local_decisions:
                    condition &= records.c.kind.in_(query.kinds)
                for column, value in (
                    (literal(self.owner) if local_decisions else records.c.issuer, query.issuer),
                    (decisions.c.id if local_decisions else records.c.record_id, query.record_id),
                    (table.c.subject_key, subject_key(query.subject) if query.subject else None),
                    (
                        table.c.scope_digest,
                        projection_digest(query.scope.model_dump(mode="json"))
                        if query.scope
                        else None,
                    ),
                    (table.c.policy_digest, query.policy_digest),
                    (literal(None) if local_decisions else records.c.task_id, query.task_id),
                    (literal(None) if local_decisions else records.c.attempt_id, query.attempt_id),
                ):
                    if value is not None:
                        condition &= column == value
                timestamp = decisions.c.evaluated_at if local_decisions else records.c.occurred_at
                if query.depends_on is not None:
                    ref: dict[str, str | None] = {"subject_key": subject_key(query.depends_on)}
                    if query.dependency_issuer is not None:
                        ref["issuer"] = query.dependency_issuer
                    dependency_condition = records.c.dependency_refs.contains([ref])
                    if query.dependency_issuer and query.include_legacy_dependencies:
                        dependency_condition |= records.c.dependency_refs.contains(
                            [{"subject_key": ref["subject_key"], "issuer": None}]
                        )
                    condition &= dependency_condition
                if query.since:
                    condition &= timestamp >= query.since
                if query.until:
                    condition &= timestamp < query.until
                rows: Any = conn.execute(
                    select(
                        table.c.sequence,
                        decisions.c.body if local_decisions else records.c.envelope,
                    )
                    .where(condition)
                    .order_by(table.c.sequence)
                    .limit(limit + 1)
                ).all()
        items: list[Record | Decision] = []
        used, through = 0, cursor.after
        for sequence, envelope in rows[:limit]:
            item = (
                Decision.model_validate(envelope)
                if local_decisions
                else verify(envelope, self.principals, require_authority=False)
            )
            size = len(item.model_dump_json().encode())
            if size > byte_limit:
                raise ValueError("one inspection record exceeds byte bound; it cannot be skipped")
            if used + size > byte_limit:
                break
            items.append(item)
            used += size
            through = int(sequence)
        complete = len(items) == len(rows)
        progress = cursor.model_copy(update={"after": cursor.upper if complete else through})
        return RecordPage(
            items=tuple(items),
            snapshot=progress,
            next_cursor=None if complete else progress,
            encoded_bytes=used,
        )

    def read_records(self, kind: str, limit: int = 1000) -> list[Record]:
        if not 1 <= limit <= 10000:
            raise ValueError("invalid result limit")
        with self.engine.connect() as conn:
            rows: Any = (
                conn.execute(
                    select(records.c.envelope)
                    .where(records.c.kind == kind)
                    .order_by(records.c.received_at)
                    .limit(limit + 1)
                )
                .scalars()
                .all()
            )
        if len(rows) > limit:
            raise ValueError("record limit exceeded; use record_page with an explicit cursor")
        return [verify(row, self.principals, require_authority=False) for row in rows]

    def capabilities(self) -> list[Capability]:
        return [x for x in self.read_records("capability") if isinstance(x, Capability)]

    def evidence(self) -> list[Evidence]:
        return [x for x in self.read_records("evidence") if isinstance(x, Evidence)]

    def revocations(self) -> list[Revocation]:
        return [x for x in self.read_records("revocation") if isinstance(x, Revocation)]

    def events(self) -> list[Event]:
        return [x for x in self.read_records("event") if isinstance(x, Event)]

    def save_decision(self, decision: Decision) -> None:
        if decision.request.receiver != self.owner:
            raise ValueError("cannot decide for another owner")
        with self.engine.begin() as conn:
            prefix: int = conn.execute(
                select(feed_state.c.sequence).where(feed_state.c.id == 1).with_for_update()
            ).scalar_one()
            conn.execute(
                insert(decisions).values(
                    id=decision.id,
                    body=decision.model_dump(mode="json"),
                    sequence=prefix + 1,
                    subject_key=subject_key(decision.request.subject),
                    scope_digest=projection_digest(decision.request.scope.model_dump(mode="json")),
                    policy_digest=decision.policy_digest,
                    evaluated_at=decision.evaluated_at,
                )
            )
            conn.execute(update(feed_state).where(feed_state.c.id == 1).values(sequence=prefix + 1))

    def decision_records(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows: list[dict[str, Any]] = list(
                conn.execute(
                    select(decisions.c.body).order_by(decisions.c.sequence).limit(1001)
                ).scalars()
            )
        if len(rows) > 1000:
            raise ValueError("decision limit exceeded; use record_page with decision kind")
        return rows

    def set_budget(self, unit: str, amount: Decimal) -> None:
        """Operator-only initialization. No agent-accessible top-up API."""
        if not amount.is_finite() or amount < 0:
            raise ValueError("invalid budget")
        with self.engine.begin() as conn:
            conn.execute(insert(budgets).values(unit=unit, remaining=amount))

    def acquire(
        self,
        task_id: str,
        worker: str,
        unit: str,
        reservation: Decimal,
        seconds: int = 60,
        *,
        reclaim_expired: bool = True,
        minimum_remaining: Decimal = Decimal(0),
    ) -> int:
        with self.engine.begin() as conn:
            return self._acquire(
                conn,
                task_id,
                worker,
                unit,
                reservation,
                seconds,
                reclaim_expired=reclaim_expired,
                minimum_remaining=minimum_remaining,
            )

    def _acquire(
        self,
        conn: Connection,
        task_id: str,
        worker: str,
        unit: str,
        reservation: Decimal,
        seconds: int,
        *,
        reclaim_expired: bool = True,
        minimum_remaining: Decimal = Decimal(0),
    ) -> int:
        if (
            not reservation.is_finite()
            or reservation < 0
            or not 1 <= seconds <= 3600
            or not minimum_remaining.is_finite()
            or minimum_remaining < 0
        ):
            raise ValueError("invalid lease bounds")
        # Shared transaction helper; budget precedes lease in every reservation.
        available: Decimal = conn.execute(
            select(budgets.c.remaining).where(budgets.c.unit == unit).with_for_update()
        ).scalar_one()
        old = (
            conn.execute(select(leases).where(leases.c.task_id == task_id).with_for_update())
            .mappings()
            .one_or_none()
        )
        observed: datetime = conn.execute(select(func.clock_timestamp())).scalar_one()
        if old and (
            not reclaim_expired or old["state"] != "active" or old["expires_at"] > observed
        ):
            raise Conflict("task already owned or terminal")
        if old and old["unit"] != unit:
            raise Conflict("lease unit cannot change")
        # Expired reservations remain charged: the external effect may have occurred.
        if available < reservation + minimum_remaining:
            raise Conflict("budget exhausted")
        fence = old["fence"] + 1 if old else 1
        values = dict(
            worker=worker,
            fence=fence,
            expires_at=observed + timedelta(seconds=seconds),
            state="active",
            reservation=reservation,
            unit=unit,
        )
        if old:
            conn.execute(update(leases).where(leases.c.task_id == task_id).values(**values))
        else:
            conn.execute(insert(leases).values(task_id=task_id, **values))
        conn.execute(
            update(budgets).where(budgets.c.unit == unit).values(remaining=available - reservation)
        )
        return int(fence)

    def finish(self, task_id: str, worker: str, fence: int, *, cancelled: bool = False) -> None:
        with self.engine.begin() as conn:
            result = conn.execute(
                update(leases)
                .where(
                    (leases.c.task_id == task_id)
                    & (leases.c.worker == worker)
                    & (leases.c.fence == fence)
                    & (leases.c.state == "active")
                    & (leases.c.expires_at > func.clock_timestamp())
                )
                .values(state="cancelled" if cancelled else "complete")
            )
            if result.rowcount != 1:
                raise Conflict("stale, expired, cancelled or completed lease")


def migrate(engine: Engine, revision: str = "head") -> None:
    """Apply packaged Alembic revisions, never during import or Store construction."""
    from importlib.resources import files

    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option(
        "script_location", str(files("collective_intelligence_overlay") / "migrations")
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
