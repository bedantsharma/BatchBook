"""add fee structure and fee record tables

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-05-28 00:00:00.000000

Adds FeeStructure (one per Batch) and FeeRecord (one per Enrollment per month).
Apply after the Enrollment table migration (d1e2f3a4b5c6).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create FeeStructure and FeeRecord tables."""
    op.create_table(
        "FeeStructure",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("monthly_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["Batch.id"], name="fk_fee_structure_batch_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", name="uq_fee_structure_batch"),
    )
    op.create_index(
        op.f("ix_FeeStructure_id"), "FeeStructure", ["id"], unique=False
    )

    op.create_table(
        "FeeRecord",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount_due", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("NOT_PAID", "PARTIALLY_PAID", "FULLY_PAID", name="feestatus"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("payment_reference", sa.String(), nullable=True),
        sa.Column("payment_link", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["Enrollment.id"],
            name="fk_fee_record_enrollment_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "enrollment_id", "month", name="uq_fee_record_enrollment_month"
        ),
    )
    op.create_index(op.f("ix_FeeRecord_id"), "FeeRecord", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop FeeRecord and FeeStructure tables."""
    op.drop_index(op.f("ix_FeeRecord_id"), table_name="FeeRecord")
    op.drop_table("FeeRecord")
    op.drop_index(op.f("ix_FeeStructure_id"), table_name="FeeStructure")
    op.drop_table("FeeStructure")
    op.execute("DROP TYPE IF EXISTS feestatus")
