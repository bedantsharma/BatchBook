"""add teacher table

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create Teacher table."""
    op.create_table(
        "Teacher",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("institute_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["institute_id"], ["Institute.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_number"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_Teacher_id"), "Teacher", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop Teacher table."""
    op.drop_index(op.f("ix_Teacher_id"), table_name="Teacher")
    op.drop_table("Teacher")
