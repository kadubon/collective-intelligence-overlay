"""Index scoped execution/formation history without rewriting signed records."""

import hashlib
import json
from datetime import datetime
from typing import Any

from alembic import op
from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table, select, update

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.add_column("records", Column("policy_digest", String(64), nullable=True))
    conn = op.get_bind()
    table = Table("records", MetaData(), autoload_with=conn)
    after = 0
    while True:
        rows: Any = conn.execute(
            select(table.c.sequence, table.c.body)
            .where((table.c.kind == "event") & (table.c.sequence > after))
            .order_by(table.c.sequence)
            .limit(128)
        ).all()
        if not rows:
            break
        for sequence, body in rows:
            receipt = body.get("execution") or body.get("formation")
            if receipt:
                scope_digest = hashlib.sha256(
                    json.dumps(receipt["scope"], sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                conn.execute(
                    update(table)
                    .where(table.c.sequence == sequence)
                    .values(scope_digest=scope_digest, policy_digest=receipt["policy_digest"])
                )
            after = sequence
    op.create_index("ix_record_scope_history", "records", ["kind", "scope_digest", "sequence"])
    op.create_index("ix_record_policy_history", "records", ["policy_digest", "sequence"])
    for name, type_ in (
        ("sequence", BigInteger()),
        ("subject_key", String(64)),
        ("scope_digest", String(64)),
        ("policy_digest", String(64)),
        ("evaluated_at", DateTime(timezone=True)),
    ):
        op.add_column("decisions", Column(name, type_, nullable=True))
    decision_table = Table("decisions", MetaData(), autoload_with=conn)
    state = Table("feed_state", MetaData(), autoload_with=conn)
    prefix: Any = conn.execute(select(state.c.sequence).with_for_update()).scalar_one()
    last = ""
    while True:
        batch: Any = conn.execute(
            select(decision_table.c.id, decision_table.c.body)
            .where(decision_table.c.id > last)
            .order_by(decision_table.c.id)
            .limit(128)
        ).all()
        if not batch:
            break
        for identifier, body in batch:
            prefix += 1
            request = body["request"]
            subject = request["subject"]
            conn.execute(
                update(decision_table)
                .where(decision_table.c.id == identifier)
                .values(
                    sequence=prefix,
                    subject_key=_hash([subject["id"], subject["version"], subject["digest"]]),
                    scope_digest=_hash(request["scope"]),
                    policy_digest=body["policy_digest"],
                    evaluated_at=datetime.fromisoformat(body["evaluated_at"]),
                )
            )
            last = identifier
    conn.execute(update(state).values(sequence=prefix))
    for name in ("sequence", "subject_key", "scope_digest", "policy_digest", "evaluated_at"):
        op.alter_column("decisions", name, nullable=False)
    op.create_index("ix_decision_sequence", "decisions", ["sequence"], unique=True)
    op.create_index("ix_decision_subject", "decisions", ["subject_key", "sequence"])
    op.create_index("ix_decision_scope", "decisions", ["scope_digest", "policy_digest", "sequence"])
    op.create_index("ix_decision_time", "decisions", ["evaluated_at", "sequence"])


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def downgrade() -> None:
    raise RuntimeError("restore a consistent backup rather than discard inspection projections")
