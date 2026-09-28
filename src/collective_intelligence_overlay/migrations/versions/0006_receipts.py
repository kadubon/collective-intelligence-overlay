"""Link durable invocations to their signed execution receipts."""

from alembic import op
from sqlalchemy import Column, String

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.add_column("invocations", Column("receipt_id", String(160), nullable=True))
    op.create_index("ix_invocation_receipt", "invocations", ["receipt_id"])


def downgrade() -> None:
    raise RuntimeError(
        "restore a consistent backup; observed receipts cannot be invented or discarded"
    )
