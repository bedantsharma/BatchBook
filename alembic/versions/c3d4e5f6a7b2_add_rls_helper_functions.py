"""add rls helper functions

Revision ID: c3d4e5f6a7b2
Revises: c3d4e5f6a7b1
Create Date: 2026-06-15 11:05:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b2'
down_revision: str | Sequence[str] | None = 'c3d4e5f6a7b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# asyncpg prepares each op.execute() call as a single command, so the
# schema/functions/grants must be issued as separate statements rather
# than one multi-statement string.
STATEMENTS = [
    'create schema if not exists private',

    # Owner.id for the current authenticated user, or null
    """
    create or replace function private.current_owner_id()
    returns integer
    language sql stable security definer set search_path = ''
    as $$
      select id from public."Owner" where teacher_id = (select auth.uid())
    $$
    """,

    # Institute.id owned by the current authenticated user, or null
    """
    create or replace function private.owner_institute_id()
    returns integer
    language sql stable security definer set search_path = ''
    as $$
      select id from public."Institute" where owner_id = private.current_owner_id()
    $$
    """,

    # Parent.id for the current authenticated user, or null
    """
    create or replace function private.current_parent_id()
    returns integer
    language sql stable security definer set search_path = ''
    as $$
      select id from public."Parent" where user_id = (select auth.uid())
    $$
    """,

    # Institute.id that a given Batch belongs to
    """
    create or replace function private.batch_institute_id(p_batch_id integer)
    returns integer
    language sql stable security definer set search_path = ''
    as $$
      select institute_id from public."Batch" where id = p_batch_id
    $$
    """,

    # Institute.id that a given Enrollment belongs to (via its Batch)
    """
    create or replace function private.enrollment_institute_id(p_enrollment_id integer)
    returns integer
    language sql stable security definer set search_path = ''
    as $$
      select b.institute_id
      from public."Enrollment" e
      join public."Batch" b on b.id = e.batch_id
      where e.id = p_enrollment_id
    $$
    """,

    # True if a child of the current parent is enrolled in this batch
    """
    create or replace function private.is_parent_batch(p_batch_id integer)
    returns boolean
    language sql stable security definer set search_path = ''
    as $$
      select exists (
        select 1 from public."Enrollment" e
        join public."Student" s on s.id = e.student_id
        where e.batch_id = p_batch_id and s.parent_id = private.current_parent_id()
      )
    $$
    """,

    # True if this enrollment belongs to a child of the current parent
    """
    create or replace function private.is_parent_enrollment(p_enrollment_id integer)
    returns boolean
    language sql stable security definer set search_path = ''
    as $$
      select exists (
        select 1 from public."Enrollment" e
        where e.id = p_enrollment_id and e.student_id in (
          select id from public."Student" where parent_id = private.current_parent_id()
        )
      )
    $$
    """,

    'grant usage on schema private to authenticated',
    'grant execute on all functions in schema private to authenticated',
]


def upgrade() -> None:
    """Upgrade schema."""
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("drop schema if exists private cascade")
