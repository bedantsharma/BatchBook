"""institute razorpay payout fields

Revision ID: i3j4k5l6m7n8
Revises: 00f800b106b9
Create Date: 2026-07-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "i3j4k5l6m7n8"
down_revision: str | Sequence[str] | None = "00f800b106b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAZORPAY_STATUS_VALUES = ("NOT_CONNECTED", "CONNECTED", "NEEDS_RECONNECT")


def upgrade() -> None:
    # ALTER TABLE ADD COLUMN does not auto-emit CREATE TYPE the way CREATE TABLE
    # does, so the enum type must be created explicitly first. The column then
    # references the same type with create_type=False so add_column's DDL
    # compilation doesn't try (and fail) to create it a second time.
    postgresql.ENUM(*RAZORPAY_STATUS_VALUES, name="razorpaystatus").create(
        op.get_bind(), checkfirst=True
    )

    op.add_column("Institute", sa.Column("razorpay_key_id", sa.String(), nullable=True))
    op.add_column(
        "Institute", sa.Column("razorpay_key_secret_encrypted", sa.String(), nullable=True)
    )
    op.add_column(
        "Institute",
        sa.Column(
            "razorpay_status",
            postgresql.ENUM(*RAZORPAY_STATUS_VALUES, name="razorpaystatus", create_type=False),
            nullable=False,
            server_default="NOT_CONNECTED",
        ),
    )


def downgrade() -> None:
    op.drop_column("Institute", "razorpay_status")
    op.drop_column("Institute", "razorpay_key_secret_encrypted")
    op.drop_column("Institute", "razorpay_key_id")
    postgresql.ENUM(name="razorpaystatus").drop(op.get_bind(), checkfirst=True)
