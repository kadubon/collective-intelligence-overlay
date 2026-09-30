"""Project observation instances and owner commands without changing signed records."""

from alembic import op
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    select,
)
from sqlalchemy.dialects.postgresql import insert

from collective_intelligence_overlay.bindings import fingerprint

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.create_table(
        "work_opportunity_instances",
        Column("owner", String(160), primary_key=True),
        Column("opportunity_id", String(160), primary_key=True),
        Column("cause_id", String(64)),
        Column("issue_sequence", BigInteger, nullable=False),
        Column("reissue_count", Integer),
        Column("last_reissued_at", DateTime(timezone=True)),
        Column("new_attempt_requested", Boolean, nullable=False, server_default="false"),
        Column("reissue_reason", String(160)),
    )
    op.create_index(
        "ix_opportunity_cause_sequence",
        "work_opportunity_instances",
        ["owner", "cause_id", "issue_sequence"],
    )
    op.create_table(
        "work_reobservations",
        Column("owner", String(160), primary_key=True),
        Column("request_id", String(160), primary_key=True),
        Column("fingerprint", String(64), nullable=False),
        Column("result", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    op.add_column("work_selections", Column("cause_id", String(64)))
    op.add_column("work_selections", Column("invocation_id", String(160)))
    op.create_index("ix_selection_cause", "work_selections", ["owner", "cause_id"])
    op.create_index("ix_selection_invocation", "work_selections", ["owner", "invocation_id"])
    conn = op.get_bind()
    tables = MetaData()
    tables.reflect(conn, only=["records", "work_selections", "work_opportunity_instances"])
    records, choices, instances = (
        tables.tables[name] for name in ("records", "work_selections", "work_opportunity_instances")
    )
    # Original sequence and explicit contract are known. Historical counts/times
    # and missing contracts are not: leave those NULL, never reconstruct DSSE.
    rows = conn.execute(
        select(records.c.issuer, records.c.record_id, records.c.body, records.c.sequence).where(
            records.c.kind == "opportunity"
        )
    )
    for row in rows:
        contract = row.body.get("goal_contract_digest")
        cause = (
            None
            if contract is None
            else fingerprint({"owner": row.issuer, "goal": row.body["goal_id"]})
        )
        conn.execute(
            insert(instances).values(
                owner=row.issuer,
                opportunity_id=row.record_id,
                cause_id=cause,
                issue_sequence=row.sequence,
            )
        )
        conn.execute(
            choices.update()
            .where((choices.c.owner == row.issuer) & (choices.c.opportunity_id == row.record_id))
            .values(cause_id=cause)
        )
    for row in conn.execute(select(choices.c.owner, choices.c.opportunity_id, choices.c.body)):
        conn.execute(
            choices.update()
            .where(
                (choices.c.owner == row.owner) & (choices.c.opportunity_id == row.opportunity_id)
            )
            .values(invocation_id=row.body["invocation_id"])
        )


def downgrade() -> None:
    raise RuntimeError("restore a consistent backup; reobservation receipts cannot be discarded")
