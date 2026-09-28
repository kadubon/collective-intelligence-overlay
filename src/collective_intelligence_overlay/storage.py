"""One owner's PostgreSQL store. Migrations are explicit, records append-only."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from .models import Capability, Decision, Event, Evidence, Record, Revocation, now
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
)
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


class Store:
    def __init__(self, url: str, owner: str, principals: dict[str, Principal]) -> None:
        if not url.startswith("postgresql+pg8000://"):
            raise ValueError("reference storage requires PostgreSQL with pg8000")
        self.owner = owner
        self.principals = dict(principals)
        self.engine: Engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)

    def close(self) -> None:
        self.engine.dispose()

    def put(self, envelope: dict[str, Any]) -> bool:
        record = verify(envelope, self.principals)
        with self.engine.begin() as conn:
            return self._insert(conn, record, envelope)

    @staticmethod
    def _insert(conn: Connection, record: Record, envelope: dict[str, Any]) -> bool:
        key = record.subject.key if isinstance(record, Capability) else record.id
        body = record.model_dump(mode="json")
        selector = (
            (records.c.kind == record.kind)
            & (records.c.issuer == record.issuer)
            & (records.c.record_id == key)
        )
        result = conn.execute(
            pg_insert(records)
            .values(
                kind=record.kind,
                issuer=record.issuer,
                record_id=key,
                body=body,
                envelope=envelope,
                received_at=now(),
            )
            .on_conflict_do_nothing()
        )
        if result.rowcount == 0:
            old: Any = conn.execute(select(records.c.body).where(selector)).scalar_one()
            if old != body:
                raise Conflict("record identity conflict")
            return False
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
                    actual=None if cancelled else row["reservation"],
                )
            )

    def record_count(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(records)).scalar_one())

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
        if not reservation.is_finite() or reservation < 0 or not 1 <= seconds <= 3600:
            raise ValueError("invalid lease bounds")
        # Lock budget first for consistent lock ordering across acquire/settle.
        with self.engine.begin() as conn:
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
                update(budgets)
                .where(budgets.c.unit == unit)
                .values(remaining=available - reservation)
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


def migrate(engine: Engine) -> None:
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
        command.upgrade(config, "head")
