"""add test score table

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-31 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "TestScore",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("test_name", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("max_marks", sa.Integer(), nullable=False),
        sa.Column("obtained_marks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["Enrollment.id"], name="fk_test_score_enrollment_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_TestScore_id"), "TestScore", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_TestScore_id"), table_name="TestScore")
    op.drop_table("TestScore")
