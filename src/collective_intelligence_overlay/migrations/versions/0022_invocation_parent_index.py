"""Index owner-local v6 child anchors without inventing historical lineage."""

from alembic import op

revision = "0022"
down_revision = "0021"


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_records_invocation_parent ON records "
        "(issuer, (CAST(body -> 'invocation_observation' ->> 'parent_invocation' AS VARCHAR))) "
        "WHERE kind = 'event' AND "
        "CAST(body -> 'invocation_observation' ->> 'phase' AS VARCHAR) = 'accepted'"
    )


def downgrade() -> None:
    op.drop_index("ix_records_invocation_parent", table_name="records")
