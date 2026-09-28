"""Indexed projections and a transactional publication prefix.

Original records/envelopes and the immutable 0001 revision are untouched.
DDL/backfill run in one transaction: interruption rolls back and upgrade retries.
"""

import base64
import hashlib
import json
from typing import Any
from uuid import uuid4

from alembic import op
from sqlalchemy import BigInteger, Column, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"


def hashed(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def upgrade() -> None:
    for column in (
        Column("sequence", BigInteger, nullable=True),
        Column("subject_key", String(64), nullable=True),
        Column("subject_id", String(160), nullable=True),
        Column("subject_version", String(160), nullable=True),
        Column("subject_digest", String(64), nullable=True),
        Column("claim", String(160), nullable=True),
        Column("evidence_id", String(160), nullable=True),
        Column("scope_digest", String(64), nullable=True),
        Column("receivers", JSONB, nullable=True),
        Column("task_id", String(160), nullable=True),
        Column("attempt_id", String(160), nullable=True),
        Column("occurred_at", DateTime(timezone=True), nullable=True),
    ):
        op.add_column("records", column)
    op.create_table(
        "feed_state",
        Column("id", Integer, primary_key=True),
        Column("generation", String(64), nullable=False),
        Column("sequence", BigInteger, nullable=False),
    )
    op.create_table(
        "subject_revisions",
        Column("subject_key", String(64), primary_key=True),
        Column("revision", BigInteger, nullable=False),
    )
    conn = op.get_bind()
    # Exclusive maintenance upgrade; stop all 0.1 writers before applying it.
    conn.execute(text("LOCK TABLE records IN ACCESS EXCLUSIVE MODE"))
    after = None
    sequence = 0
    while True:
        clause = "WHERE (kind,issuer,record_id) > (:k,:i,:r)" if after else ""
        batch = (
            conn.execute(
                text(
                    "SELECT kind,issuer,record_id,envelope FROM records "
                    + clause
                    + " ORDER BY kind,issuer,record_id LIMIT 256"
                ),
                dict(zip(("k", "i", "r"), after, strict=True)) if after else {},
            )
            .mappings()
            .all()
        )
        if not batch:
            break
        for row in batch:
            payload = json.loads(base64.b64decode(row["envelope"]["payload"]))
            subject = payload["subject"]
            key = hashed([subject["id"], subject["version"], subject["digest"]])
            scope = payload.get("scope")
            sequence += 1
            conn.execute(
                text("""
                UPDATE records SET sequence=:sequence, subject_key=:key,
                  subject_id=:sid, subject_version=:version, subject_digest=:digest,
                  claim=:claim, evidence_id=:evidence_id, scope_digest=:scope,
                  receivers=CAST(:receivers AS jsonb),
                  task_id=:task, attempt_id=:attempt, occurred_at=:occurred
                WHERE kind=:kind AND issuer=:issuer AND record_id=:rid
            """),
                {
                    "sequence": sequence,
                    "key": key,
                    "sid": subject["id"],
                    "version": subject["version"],
                    "digest": subject["digest"],
                    "claim": payload.get("claim"),
                    "evidence_id": payload.get("evidence_id"),
                    "scope": hashed(scope) if scope else None,
                    "receivers": json.dumps(payload.get("receivers", [])),
                    "task": payload.get("task_id"),
                    "attempt": payload.get("attempt_id"),
                    "occurred": payload.get("occurred_at", payload.get("created_at")),
                    "kind": row["kind"],
                    "issuer": row["issuer"],
                    "rid": row["record_id"],
                },
            )
            if row["kind"] != "event":
                conn.execute(
                    text("""
                    INSERT INTO subject_revisions(subject_key, revision) VALUES (:key,1)
                    ON CONFLICT(subject_key) DO UPDATE
                    SET revision=subject_revisions.revision+1
                """),
                    {"key": key},
                )
        last = batch[-1]
        after = (last["kind"], last["issuer"], last["record_id"])
    op.alter_column("records", "sequence", nullable=False)
    conn.execute(
        text("INSERT INTO feed_state(id,generation,sequence) VALUES (1,:g,:s)"),
        {"g": uuid4().hex, "s": sequence},
    )
    op.create_index("ix_records_sequence", "records", ["sequence"], unique=True)
    op.create_index("ix_records_subject", "records", ["subject_key", "kind", "issuer"])
    op.create_index("ix_records_withdrawal", "records", ["evidence_id", "issuer"])
    op.create_index(
        "ix_records_evidence_scope", "records", ["subject_key", "scope_digest", "claim"]
    )
    op.create_index("ix_records_receivers", "records", ["receivers"], postgresql_using="gin")
    op.create_index("ix_records_task", "records", ["task_id", "attempt_id", "sequence"])
    op.create_index("ix_records_events", "records", ["kind", "occurred_at", "sequence"])
    op.create_index("ix_dependencies_reverse", "dependencies", ["child", "digest"])


def downgrade() -> None:
    raise RuntimeError("restore a consistent pre-upgrade backup; no lossy downgrade")
