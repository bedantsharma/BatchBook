"""institute join_code + parent institute_id

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-06-14

"""
from alembic import op
import sqlalchemy as sa

revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Institute.join_code ────────────────────────────────────────────────────
    # Add nullable first so existing rows don't violate NOT NULL during backfill
    op.add_column("Institute", sa.Column("join_code", sa.String(8), nullable=True))

    # Backfill existing institutes with a random 8-char hex code (first 8 chars of md5)
    op.execute(
        "UPDATE \"Institute\" SET join_code = UPPER(SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT), 1, 8))"
    )

    # Now enforce NOT NULL + UNIQUE
    op.alter_column("Institute", "join_code", nullable=False)
    op.create_unique_constraint("uq_institute_join_code", "Institute", ["join_code"])
    op.create_index("ix_institute_join_code", "Institute", ["join_code"])

    # ── Parent.user_id now nullable (parent pre-created by owner before OTP) ──
    op.alter_column("Parent", "user_id", nullable=True)

    # ── Parent.institute_id ────────────────────────────────────────────────────
    op.add_column(
        "Parent",
        sa.Column("institute_id", sa.Integer(), sa.ForeignKey("Institute.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("Parent", "institute_id")
    op.alter_column("Parent", "user_id", nullable=False)
    op.drop_index("ix_institute_join_code", table_name="Institute")
    op.drop_constraint("uq_institute_join_code", "Institute", type_="unique")
    op.drop_column("Institute", "join_code")
