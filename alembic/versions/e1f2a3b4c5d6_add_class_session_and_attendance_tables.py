"""add class_session and attendance tables

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-05-30 00:00:00.000000

NOTE: This migration depends on the Enrollment table (revision d1e2f3a4b5c6) and
the Batch table (revision c1d2e3f4a5b6).
Apply those migrations before running this one.
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
    """Upgrade schema: create ClassSession and Attendance tables."""
    op.create_table(
        "ClassSession",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["Batch.id"], name="fk_class_session_batch_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ClassSession_id"), "ClassSession", ["id"], unique=False)

    op.create_table(
        "Attendance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PRESENT", "ABSENT", "LATE", name="attendancestatus"),
            nullable=False,
        ),
        sa.Column("marked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["enrollment_id"],
            ["Enrollment.id"],
            name="fk_attendance_enrollment_id",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["ClassSession.id"],
            name="fk_attendance_session_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "enrollment_id",
            name="uq_attendance_session_enrollment",
        ),
    )
    op.create_index(op.f("ix_Attendance_id"), "Attendance", ["id"], unique=False)


def downgrade() -> None:
    """Downgrade schema: drop Attendance and ClassSession tables."""
    op.drop_index(op.f("ix_Attendance_id"), table_name="Attendance")
    op.drop_table("Attendance")
    op.drop_enum("attendancestatus")
    op.drop_index(op.f("ix_ClassSession_id"), table_name="ClassSession")
    op.drop_table("ClassSession")
