"""Owner-local observation bookkeeping; execution stays in Selection/Executor."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, String, Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, RowMapping

from .bindings import fingerprint
from .models import Decision, Digest, Identifier, Opportunity, now
from .security import Identity, verify
from .storage import Conflict, Store, decisions, feed_state, metadata, records

instances = Table(
    "work_opportunity_instances",
    metadata,
    Column("owner", String(160), primary_key=True),
    Column("opportunity_id", String(160), primary_key=True),
    Column("cause_id", String(64)),
    Column("issue_sequence", BigInteger, nullable=False),
    Column("reissue_count", Integer),
    Column("last_reissued_at", DateTime(timezone=True)),
    Column("new_attempt_requested", Boolean, nullable=False, server_default="false"),
    Column("reissue_reason", String(160)),
)
requests = Table(
    "work_reobservations",
    metadata,
    Column("owner", String(160), primary_key=True),
    Column("request_id", String(160), primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("result", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class ReobservationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cooldown_seconds: int = Field(default=60, ge=1, le=86400)
    max_reissues: int = Field(default=3, ge=1, le=16)


class Reobservation(BaseModel):
    """An observation receipt, never a new execution or allowance grant."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    state: Literal["issued", "existing_instance", "satisfied", "cooldown", "reissue_limit"]
    cause_id: Digest
    opportunity: Opportunity | None
    reissue_count: int = Field(ge=0, le=16)
    reason: Identifier
    observed_at: AwareDatetime
    replayed: bool = False


def cause_id(owner: str, goal_id: str) -> str:
    # The owner goal namespace remains stable across target/checker revisions.
    # Contract pins are checked separately; changing one cannot hide old UNKNOWN.
    return fingerprint({"owner": owner, "goal": goal_id})


class ObservationLedger:
    """Two small projections on the existing owner database and feed transaction.

    The instance index retains cause/count/intent. Command receipts deduplicate
    retries, including requests that issued nothing. Neither tracks execution.
    """

    def __init__(self, store: Store, identity: Identity) -> None:
        if store.owner != identity.name:
            raise ValueError("observation bookkeeping belongs to the local owner")
        self.store, self.identity = store, identity

    def replay(self, request_id: str, request_fingerprint: str) -> Reobservation | None:
        with self.store.engine.connect() as conn:
            return self._replay(conn, request_id, request_fingerprint)

    def is_current(self, opportunity_id: str) -> bool:
        with self.store.engine.connect() as conn:
            cause = conn.execute(
                select(instances.c.cause_id).where(
                    (instances.c.owner == self.store.owner)
                    & (instances.c.opportunity_id == opportunity_id)
                )
            ).scalar_one_or_none()
            if cause is None:
                return False
            return (
                conn.execute(
                    select(instances.c.opportunity_id)
                    .where(
                        (instances.c.owner == self.store.owner) & (instances.c.cause_id == cause)
                    )
                    .order_by(instances.c.issue_sequence.desc())
                    .limit(1)
                ).scalar_one()
                == opportunity_id
            )

    def _replay(
        self, conn: Connection, request_id: str, request_fingerprint: str
    ) -> Reobservation | None:
        row = (
            conn.execute(
                select(requests).where(
                    (requests.c.owner == self.store.owner) & (requests.c.request_id == request_id)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        if row["fingerprint"] != request_fingerprint:
            raise Conflict("reobservation request ID reused with different arguments")
        return Reobservation.model_validate(row["result"]).model_copy(update={"replayed": True})

    def _latest(self, conn: Connection, cause: str) -> tuple[Opportunity, RowMapping] | None:
        row = (
            conn.execute(
                select(instances, records.c.envelope)
                .select_from(
                    instances.join(
                        records,
                        (records.c.kind == "opportunity")
                        & (records.c.issuer == instances.c.owner)
                        & (records.c.record_id == instances.c.opportunity_id),
                    )
                )
                .where((instances.c.owner == self.store.owner) & (instances.c.cause_id == cause))
                .order_by(instances.c.issue_sequence.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        item = verify(row["envelope"], self.store.principals)
        if not isinstance(item, Opportunity) or item.issuer != self.store.owner:
            raise ValueError("stored instance is not a local signed opportunity")
        return item, row

    def _insert(
        self,
        conn: Connection,
        item: Opportunity,
        cause: str,
        reissues: int,
        last_reissued_at: datetime | None,
        new_attempt: bool,
        reason: str | None,
    ) -> None:
        signed = self.identity.sign(item)
        self.store._insert(conn, verify(signed, self.store.principals), signed)
        sequence: int = conn.execute(
            select(records.c.sequence).where(
                (records.c.kind == "opportunity")
                & (records.c.issuer == self.store.owner)
                & (records.c.record_id == item.id)
            )
        ).scalar_one()
        conn.execute(
            insert(instances)
            .values(
                owner=self.store.owner,
                opportunity_id=item.id,
                cause_id=cause,
                issue_sequence=sequence,
                reissue_count=reissues,
                last_reissued_at=last_reissued_at,
                new_attempt_requested=new_attempt,
                reissue_reason=reason,
            )
            .on_conflict_do_nothing()
        )

    def _check_revisions(self, conn: Connection, candidate: Opportunity | None) -> None:
        if candidate is None:
            return
        for reference in candidate.basis:
            # Decisions are immutable owner-local inputs, not untrusted replies.
            row: Any = conn.execute(
                select(decisions.c.body).where(decisions.c.id == reference.id)
            ).scalar_one()
            decision = Decision.model_validate(row)
            if decision.revisions != self.store._revisions(conn, set(decision.revisions)):
                raise Conflict("observation changed before publication; reobserve again")

    def _closed_selected_instance(self, conn: Connection, opportunity_id: str) -> bool:
        from .invocations import invocations, released_before_dispatch
        from .steps import selections
        from .storage import leases

        invocation_id = conn.execute(
            select(selections.c.invocation_id).where(
                (selections.c.owner == self.store.owner)
                & (selections.c.opportunity_id == opportunity_id)
            )
        ).scalar_one_or_none()
        if invocation_id is None:
            return False
        row = (
            conn.execute(
                select(invocations).where(
                    (invocations.c.owner == self.store.owner)
                    & (invocations.c.caller == self.store.owner)
                    & (invocations.c.id == invocation_id)
                )
            )
            .mappings()
            .first()
        )
        lease = (
            None
            if row is None
            else conn.execute(select(leases).where(leases.c.task_id == row["lease_id"]))
            .mappings()
            .first()
        )
        return released_before_dispatch(row, lease)

    def publish(
        self, candidate: Opportunity, cause: str, lifetime_seconds: int
    ) -> tuple[Opportunity, bool, bool]:
        """Publish a changed semantic observation; time alone never mints one."""
        with self.store.engine.begin() as conn:
            conn.execute(
                select(feed_state.c.sequence).where(feed_state.c.id == 1).with_for_update()
            ).one()
            self._check_revisions(conn, candidate)
            latest = self._latest(conn, cause)
            if latest is not None and latest[0].observation_digest == candidate.observation_digest:
                return latest[0], False, False
            previous = conn.execute(
                select(records.c.envelope).where(
                    (records.c.kind == "opportunity")
                    & (records.c.issuer == self.store.owner)
                    & (records.c.record_id == candidate.id)
                )
            ).scalar_one_or_none()
            if previous is not None:
                item = verify(previous, self.store.principals)
                if (
                    not isinstance(item, Opportunity)
                    or item.observation_digest != candidate.observation_digest
                ):
                    raise Conflict("opportunity identity does not match observation")
                if latest is None:
                    sequence = conn.execute(
                        select(records.c.sequence).where(
                            (records.c.kind == "opportunity")
                            & (records.c.issuer == self.store.owner)
                            & (records.c.record_id == item.id)
                        )
                    ).scalar_one()
                    conn.execute(
                        insert(instances)
                        .values(
                            owner=self.store.owner,
                            opportunity_id=item.id,
                            cause_id=cause,
                            issue_sequence=sequence,
                            new_attempt_requested=False,
                        )
                        .on_conflict_do_update(
                            index_elements=[instances.c.owner, instances.c.opportunity_id],
                            set_={"cause_id": cause},
                        )
                    )
                return item, False, latest is not None and latest[0].id != item.id
            issued_at = now()
            item = candidate.model_copy(
                update={
                    "created_at": issued_at,
                    "expires_at": issued_at + timedelta(seconds=lifetime_seconds),
                    "supersedes": latest[0].id if latest else None,
                }
            )
            self._insert(
                conn,
                item,
                cause,
                int(latest[1]["reissue_count"] or 0) if latest else 0,
                latest[1]["last_reissued_at"] if latest else None,
                latest is not None and latest[0].goal_digest != item.goal_digest,
                None,
            )
            return item, True, False

    def renew(
        self,
        candidate: Opportunity | None,
        previous: Opportunity,
        cause: str,
        request_id: str,
        request_fingerprint: str,
        reason: str,
        new_attempt: bool,
        policy: ReobservationPolicy,
        lifetime_seconds: int,
    ) -> Reobservation:
        with self.store.engine.begin() as conn:
            conn.execute(
                select(feed_state.c.sequence).where(feed_state.c.id == 1).with_for_update()
            ).one()
            replay = self._replay(conn, request_id, request_fingerprint)
            if replay is not None:
                return replay
            self._check_revisions(conn, candidate)
            latest = self._latest(conn, cause)
            if latest is None:
                # Explicit adoption has already checked the exact registered goal.
                sequence: int = conn.execute(
                    select(records.c.sequence).where(
                        (records.c.kind == "opportunity")
                        & (records.c.issuer == self.store.owner)
                        & (records.c.record_id == previous.id)
                    )
                ).scalar_one()
                conn.execute(
                    insert(instances)
                    .values(
                        owner=self.store.owner,
                        opportunity_id=previous.id,
                        cause_id=cause,
                        issue_sequence=sequence,
                        new_attempt_requested=False,
                    )
                    .on_conflict_do_update(
                        index_elements=[instances.c.owner, instances.c.opportunity_id],
                        set_={"cause_id": cause},
                    )
                )
                latest = self._latest(conn, cause)
            assert latest is not None
            current, state = latest
            count = int(state["reissue_count"] or 0)
            timestamp = now()
            status: Literal["issued", "existing_instance", "satisfied", "cooldown", "reissue_limit"]
            if candidate is None:
                status, item = "satisfied", None
            elif (
                current.observation_digest == candidate.observation_digest
                and current.expires_at > timestamp
                and not (
                    new_attempt
                    and current.id == previous.id
                    and self._closed_selected_instance(conn, current.id)
                )
            ):
                # A grant request may mark a never-selected observation. It cannot
                # bypass the separate terminal-state/fencing checks in Selection.
                conn.execute(
                    instances.update()
                    .where(
                        (instances.c.owner == self.store.owner)
                        & (instances.c.opportunity_id == current.id)
                    )
                    .values(new_attempt_requested=state["new_attempt_requested"] or new_attempt)
                )
                status, item = "existing_instance", current
            elif count >= policy.max_reissues:
                status, item = "reissue_limit", current
            elif timestamp < (state["last_reissued_at"] or current.created_at) + timedelta(
                seconds=policy.cooldown_seconds
            ):
                status, item = "cooldown", current
            else:
                count += 1
                item = candidate.model_copy(
                    update={
                        "id": "op-re-"
                        + fingerprint(
                            [cause, current.id, request_id, candidate.observation_digest]
                        ),
                        "supersedes": current.id,
                        "created_at": timestamp,
                        "expires_at": timestamp + timedelta(seconds=lifetime_seconds),
                    }
                )
                self._insert(conn, item, cause, count, timestamp, new_attempt, reason)
                status = "issued"
            result = Reobservation(
                state=status,
                cause_id=cause,
                opportunity=item,
                reissue_count=count,
                reason=reason,
                observed_at=timestamp,
            )
            conn.execute(
                insert(requests).values(
                    owner=self.store.owner,
                    request_id=request_id,
                    fingerprint=request_fingerprint,
                    result=result.model_dump(mode="json"),
                    created_at=timestamp,
                )
            )
            return result
