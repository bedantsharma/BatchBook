"""institute razorpay webhook secret

Revision ID: a24386059615
Revises: i3j4k5l6m7n8
Create Date: 2026-07-03 11:48:03.445487

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a24386059615"
down_revision: str | Sequence[str] | None = "i3j4k5l6m7n8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "Institute", sa.Column("razorpay_webhook_secret_encrypted", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("Institute", "razorpay_webhook_secret_encrypted")
