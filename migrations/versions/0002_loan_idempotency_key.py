"""loans.idempotency_key for safe client retries across instances

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("loans", sa.Column("idempotency_key", sa.String(64), nullable=True))
    op.create_index(
        "ux_loans_member_idempotency", "loans", ["member_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_loans_member_idempotency", table_name="loans")
    op.drop_column("loans", "idempotency_key")
