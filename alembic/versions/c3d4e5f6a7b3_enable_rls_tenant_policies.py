"""enable rls and create tenant policies

Revision ID: c3d4e5f6a7b3
Revises: c3d4e5f6a7b2
Create Date: 2026-06-15 11:10:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b3'
down_revision: str | Sequence[str] | None = 'c3d4e5f6a7b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table_name, [policy_names])
TABLE_POLICIES = [
    ('Owner', ['owner_select_own', 'owner_update_own', 'owner_insert_own']),
    ('Institute', ['institute_owner_all', 'institute_parent_select', 'institute_teacher_select']),
    ('Batch', ['batch_owner_all', 'batch_parent_select']),
    ('Teacher', ['teacher_owner_all', 'teacher_self_select', 'teacher_self_update']),
    ('BatchTeacher', ['batch_teacher_owner_all']),
    ('Parent', ['parent_owner_all', 'parent_self_select', 'parent_self_update']),
    ('Student', ['student_owner_all', 'student_parent_select']),
    ('Enrollment', ['enrollment_owner_all', 'enrollment_parent_select']),
    ('FeeStructure', ['fee_structure_owner_all', 'fee_structure_parent_select']),
    ('ClassSession', ['class_session_owner_all', 'class_session_parent_select']),
    ('Attendance', ['attendance_owner_all', 'attendance_parent_select']),
    ('FeeRecord', ['fee_record_owner_all', 'fee_record_parent_select']),
    ('TestScore', ['test_score_owner_all', 'test_score_parent_select']),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        -- Owner
        alter table public."Owner" enable row level security;

        create policy "owner_select_own" on public."Owner"
          for select to authenticated
          using (teacher_id = (select auth.uid()));

        create policy "owner_update_own" on public."Owner"
          for update to authenticated
          using (teacher_id = (select auth.uid()))
          with check (teacher_id = (select auth.uid()));

        create policy "owner_insert_own" on public."Owner"
          for insert to authenticated
          with check (teacher_id = (select auth.uid()));

        -- Institute
        alter table public."Institute" enable row level security;

        create policy "institute_owner_all" on public."Institute"
          for all to authenticated
          using (owner_id = private.current_owner_id())
          with check (owner_id = private.current_owner_id());

        create policy "institute_parent_select" on public."Institute"
          for select to authenticated
          using (id = (select institute_id from public."Parent" where user_id = (select auth.uid())));

        create policy "institute_teacher_select" on public."Institute"
          for select to authenticated
          using (id = (select institute_id from public."Teacher" where user_id = (select auth.uid())));

        -- Batch
        alter table public."Batch" enable row level security;

        create policy "batch_owner_all" on public."Batch"
          for all to authenticated
          using (institute_id = private.owner_institute_id())
          with check (institute_id = private.owner_institute_id());

        create policy "batch_parent_select" on public."Batch"
          for select to authenticated
          using (private.is_parent_batch(id));

        -- Teacher
        alter table public."Teacher" enable row level security;

        create policy "teacher_owner_all" on public."Teacher"
          for all to authenticated
          using (institute_id = private.owner_institute_id())
          with check (institute_id = private.owner_institute_id());

        create policy "teacher_self_select" on public."Teacher"
          for select to authenticated
          using (user_id = (select auth.uid()));

        create policy "teacher_self_update" on public."Teacher"
          for update to authenticated
          using (user_id = (select auth.uid()))
          with check (user_id = (select auth.uid()));

        -- BatchTeacher
        alter table public."BatchTeacher" enable row level security;

        create policy "batch_teacher_owner_all" on public."BatchTeacher"
          for all to authenticated
          using (private.batch_institute_id(batch_id) = private.owner_institute_id())
          with check (private.batch_institute_id(batch_id) = private.owner_institute_id());

        -- Parent
        alter table public."Parent" enable row level security;

        create policy "parent_owner_all" on public."Parent"
          for all to authenticated
          using (institute_id = private.owner_institute_id())
          with check (institute_id = private.owner_institute_id());

        create policy "parent_self_select" on public."Parent"
          for select to authenticated
          using (user_id = (select auth.uid()));

        create policy "parent_self_update" on public."Parent"
          for update to authenticated
          using (user_id = (select auth.uid()))
          with check (user_id = (select auth.uid()));

        -- Student
        alter table public."Student" enable row level security;

        create policy "student_owner_all" on public."Student"
          for all to authenticated
          using (institute_id = private.owner_institute_id())
          with check (institute_id = private.owner_institute_id());

        create policy "student_parent_select" on public."Student"
          for select to authenticated
          using (parent_id = private.current_parent_id());

        -- Enrollment
        alter table public."Enrollment" enable row level security;

        create policy "enrollment_owner_all" on public."Enrollment"
          for all to authenticated
          using (private.batch_institute_id(batch_id) = private.owner_institute_id())
          with check (private.batch_institute_id(batch_id) = private.owner_institute_id());

        create policy "enrollment_parent_select" on public."Enrollment"
          for select to authenticated
          using (student_id in (select id from public."Student" where parent_id = private.current_parent_id()));

        -- FeeStructure
        alter table public."FeeStructure" enable row level security;

        create policy "fee_structure_owner_all" on public."FeeStructure"
          for all to authenticated
          using (private.batch_institute_id(batch_id) = private.owner_institute_id())
          with check (private.batch_institute_id(batch_id) = private.owner_institute_id());

        create policy "fee_structure_parent_select" on public."FeeStructure"
          for select to authenticated
          using (private.is_parent_batch(batch_id));

        -- ClassSession
        alter table public."ClassSession" enable row level security;

        create policy "class_session_owner_all" on public."ClassSession"
          for all to authenticated
          using (private.batch_institute_id(batch_id) = private.owner_institute_id())
          with check (private.batch_institute_id(batch_id) = private.owner_institute_id());

        create policy "class_session_parent_select" on public."ClassSession"
          for select to authenticated
          using (private.is_parent_batch(batch_id));

        -- Attendance
        alter table public."Attendance" enable row level security;

        create policy "attendance_owner_all" on public."Attendance"
          for all to authenticated
          using (private.enrollment_institute_id(enrollment_id) = private.owner_institute_id())
          with check (private.enrollment_institute_id(enrollment_id) = private.owner_institute_id());

        create policy "attendance_parent_select" on public."Attendance"
          for select to authenticated
          using (private.is_parent_enrollment(enrollment_id));

        -- FeeRecord
        alter table public."FeeRecord" enable row level security;

        create policy "fee_record_owner_all" on public."FeeRecord"
          for all to authenticated
          using (private.enrollment_institute_id(enrollment_id) = private.owner_institute_id())
          with check (private.enrollment_institute_id(enrollment_id) = private.owner_institute_id());

        create policy "fee_record_parent_select" on public."FeeRecord"
          for select to authenticated
          using (private.is_parent_enrollment(enrollment_id));

        -- TestScore
        alter table public."TestScore" enable row level security;

        create policy "test_score_owner_all" on public."TestScore"
          for all to authenticated
          using (private.enrollment_institute_id(enrollment_id) = private.owner_institute_id())
          with check (private.enrollment_institute_id(enrollment_id) = private.owner_institute_id());

        create policy "test_score_parent_select" on public."TestScore"
          for select to authenticated
          using (private.is_parent_enrollment(enrollment_id));
    """)


def downgrade() -> None:
    """Downgrade schema."""
    statements = []
    for table_name, policy_names in reversed(TABLE_POLICIES):
        for policy_name in reversed(policy_names):
            statements.append(f'drop policy if exists "{policy_name}" on public."{table_name}"')
        statements.append(f'alter table public."{table_name}" disable row level security')
    op.execute(";\n".join(statements) + ";")
