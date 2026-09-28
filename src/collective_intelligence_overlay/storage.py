"""One owner's PostgreSQL store. Migrations are explicit, records append-only."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
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
    Revocation,
    Subject,
    UseRequest,
    now,
)
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
)
feed_state = Table(
    "feed_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("generation", String(64), nullable=False),
    Column("sequence", BigInteger, nullable=False),
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

        @sql_event.listens_for(self.engine, "connect")
        def set_timeouts(connection: Any, _: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("SET statement_timeout = '5s'")
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET idle_in_transaction_session_timeout = '10s'")
            cursor.close()
            connection.commit()

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
        scope = body.get("scope")
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
            )
            .on_conflict_do_nothing()
        )
        if result.rowcount == 0:
            old: Any = conn.execute(select(records.c.body).where(selector)).scalar_one()
            if old != body:
                raise Conflict("record identity conflict")
            return False
        conn.execute(update(feed_state).where(feed_state.c.id == 1).values(sequence=prefix + 1))
        affected = {skey} if not isinstance(record, Event) else set()
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
        frontier = {subject_key(request.subject)}
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
                    if len(seen | frontier) > max_nodes:
                        raise ValueError("dependency closure safety bound exceeded")
                    found = fetch(
                        (records.c.kind == "capability") & records.c.subject_key.in_(frontier),
                        max_nodes * 2,
                    )
                    batch = [record for record in found if isinstance(record, Capability)]
                    caps.extend(batch)
                    seen.update(frontier)
                    frontier = {
                        subject_key(dep) for cap in batch for dep in cap.dependencies
                    } - seen

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
            raise ValueError("record limit exceeded; narrow or archive the local store")
        return [verify(row, self.principals) for row in rows]

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
            conn.execute(
                insert(decisions).values(id=decision.id, body=decision.model_dump(mode="json"))
            )

    def decision_records(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return list(conn.execute(select(decisions.c.body)).scalars())

    def set_budget(self, unit: str, amount: Decimal) -> None:
        """Operator-only initialization. No agent-accessible top-up API."""
        if not amount.is_finite() or amount < 0:
            raise ValueError("invalid budget")
        with self.engine.begin() as conn:
            conn.execute(insert(budgets).values(unit=unit, remaining=amount))

    def acquire(
        self, task_id: str, worker: str, unit: str, reservation: Decimal, seconds: int = 60
    ) -> int:
        with self.engine.begin() as conn:
            return self._acquire(conn, task_id, worker, unit, reservation, seconds)

    def _acquire(
        self,
        conn: Connection,
        task_id: str,
        worker: str,
        unit: str,
        reservation: Decimal,
        seconds: int,
    ) -> int:
        if not reservation.is_finite() or reservation < 0 or not 1 <= seconds <= 3600:
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
        if old and (old["state"] != "active" or old["expires_at"] > now()):
            raise Conflict("task already owned or terminal")
        if old and old["unit"] != unit:
            raise Conflict("lease unit cannot change")
        # Expired reservations remain charged: the external effect may have occurred.
        if available < reservation:
            raise Conflict("budget exhausted")
        fence = old["fence"] + 1 if old else 1
        values = dict(
            worker=worker,
            fence=fence,
            expires_at=now() + timedelta(seconds=seconds),
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
                    & (leases.c.expires_at > now())
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
