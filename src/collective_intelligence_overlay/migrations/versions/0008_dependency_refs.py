"""Index exact dependency subjects and known issuers without guessing legacy edges."""

import hashlib
import json
from typing import Any

from alembic import op
from sqlalchemy import Column, MetaData, Table, select, update
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.add_column("records", Column("dependency_refs", JSONB, nullable=True))
    conn = op.get_bind()
    table = Table("records", MetaData(), autoload_with=conn)
    after = 0
    while True:
        rows: Any = conn.execute(
            select(table.c.sequence, table.c.body)
            .where((table.c.kind == "capability") & (table.c.sequence > after))
            .order_by(table.c.sequence)
            .limit(128)
        ).all()
        if not rows:
            break
        for sequence, body in rows:
            issuers = body.get("dependency_issuers", [])
            refs = []
            for index, subject in enumerate(body.get("dependencies", [])):
                key = hashlib.sha256(
                    json.dumps(
                        [subject["id"], subject["version"], subject["digest"]],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                refs.append({"subject_key": key, "issuer": issuers[index] if issuers else None})
            conn.execute(
                update(table).where(table.c.sequence == sequence).values(dependency_refs=refs)
            )
            after = sequence
    op.create_index(
        "ix_records_dependency_refs", "records", ["dependency_refs"], postgresql_using="gin"
    )


def downgrade() -> None:
    raise RuntimeError("restore a verified backup; destructive downgrade is unsupported")
