"""add fk indexes for rls

Revision ID: c3d4e5f6a7b1
Revises: 8a79669dfe07
Create Date: 2026-06-15 11:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b1'
down_revision: str | Sequence[str] | None = '8a79669dfe07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEXES = [
    ("ix_batch_institute_id", '"Batch"', "institute_id"),
    ("ix_teacher_institute_id", '"Teacher"', "institute_id"),
    ("ix_parent_institute_id", '"Parent"', "institute_id"),
    ("ix_student_institute_id", '"Student"', "institute_id"),
    ("ix_student_parent_id", '"Student"', "parent_id"),
    ("ix_enrollment_batch_id", '"Enrollment"', "batch_id"),
    ("ix_enrollment_student_id", '"Enrollment"', "student_id"),
    ("ix_attendance_enrollment_id", '"Attendance"', "enrollment_id"),
    ("ix_fee_record_enrollment_id", '"FeeRecord"', "enrollment_id"),
    ("ix_test_score_enrollment_id", '"TestScore"', "enrollment_id"),
    ("ix_class_session_batch_id", '"ClassSession"', "batch_id"),
]


def upgrade() -> None:
    """Upgrade schema."""
    for index_name, table_name, column_name in INDEXES:
        op.execute(
            f'create index if not exists {index_name} on public.{table_name} ({column_name})'
        )


def downgrade() -> None:
    """Downgrade schema."""
    for index_name, _table_name, _column_name in reversed(INDEXES):
        op.execute(f'drop index if exists public.{index_name}')
