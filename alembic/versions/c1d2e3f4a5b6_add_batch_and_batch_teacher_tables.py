"""add batch and batch teacher tables

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create Batch and BatchTeacher tables."""
    op.create_table(
        "Batch",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("institute_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("grade", sa.String(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("days_of_week", sa.JSON(), nullable=False),
        sa.Column("max_capacity", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "CLOSING", "ARCHIVED", name="batchstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["institute_id"], ["Institute.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_Batch_id"), "Batch", ["id"], unique=False)

    op.create_table(
        "BatchTeacher",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["Batch.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["Teacher.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "teacher_id", name="uq_batch_teacher"),
    )
    op.create_index(op.f("ix_BatchTeacher_id"), "BatchTeacher", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop Batch and BatchTeacher tables."""
    op.drop_index(op.f("ix_BatchTeacher_id"), table_name="BatchTeacher")
    op.drop_table("BatchTeacher")
    op.drop_index(op.f("ix_Batch_id"), table_name="Batch")
    op.drop_table("Batch")
    op.execute("DROP TYPE IF EXISTS batchstatus")
