"""add enrollment table

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-05-26 00:00:00.000000

NOTE: This migration depends on the Batch table (revision c1d2e3f4a5b6).
Apply the batch migration before running this one.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create Enrollment table."""
    op.create_table(
        "Enrollment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("first_month_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["Batch.id"], name="fk_enrollment_batch_id"),
        sa.ForeignKeyConstraint(
            ["student_id"], ["Student.id"], name="fk_enrollment_student_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "batch_id", name="uq_enrollment_student_batch"
        ),
    )
    op.create_index(op.f("ix_Enrollment_id"), "Enrollment", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop Enrollment table."""
    op.drop_index(op.f("ix_Enrollment_id"), table_name="Enrollment")
    op.drop_table("Enrollment")
