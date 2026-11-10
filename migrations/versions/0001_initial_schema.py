"""initial schema: members, books, loans

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("max_active_loans", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("max_active_loans BETWEEN 1 AND 10", name="ck_members_max_loans"),
    )
    op.create_table(
        "books",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("isbn", sa.String(17), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column("published_year", sa.Integer, nullable=True),
        sa.Column("total_copies", sa.Integer, nullable=False),
        sa.Column("available_copies", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "available_copies >= 0 AND available_copies <= total_copies", name="ck_books_copies"
        ),
    )
    op.create_index("ix_books_author", "books", ["author"])
    op.create_table(
        "loans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("member_id", sa.Integer, sa.ForeignKey("members.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("borrowed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fine_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_loans_member_active", "loans", ["member_id"],
        postgresql_where=sa.text("returned_at IS NULL"),
    )
    op.create_index("ix_loans_book_id", "loans", ["book_id"])
    op.create_index("ix_loans_borrowed_at", "loans", ["borrowed_at"])
    op.create_index(
        "ux_loans_member_book_active", "loans", ["member_id", "book_id"], unique=True,
        postgresql_where=sa.text("returned_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("loans")
    op.drop_table("books")
    op.drop_table("members")
