"""add parent table and refactor student model

Revision ID: a1b2c3d4e5f6
Revises: ff13148b1b34
Create Date: 2026-05-23 00:00:00.000000

Phase 1.2 + 1.3: This migration creates the Institute table (if not already present),
adds the Parent table (for student-app auth), and refactors the Student table:
  - Removes phone_number (moves to Parent)
  - Removes user_id (moves to Parent)
  - Adds parent_id FK → Parent.id (nullable for legacy rows)
  - Adds institute_id FK → Institute.id (nullable)

RLS note: Supabase has three RLS policies on Student that reference user_id.
These are dropped before the column is removed, and new parent_id-based
policies are created in their place.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "ff13148b1b34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Institute table (Phase 1.2) ---
    op.create_table(
        "Institute",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["Owner.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id"),
    )
    op.create_index(op.f("ix_Institute_id"), "Institute", ["id"], unique=False)

    # --- Parent table (Phase 1.3) ---
    op.create_table(
        "Parent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_number"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_Parent_id"), "Parent", ["id"], unique=False)

    # --- Refactor Student table (Phase 1.3) ---
    # Add new FK columns (nullable so existing rows don't break)
    op.add_column("Student", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column("Student", sa.Column("institute_id", sa.Integer(), nullable=True))

    # Add FK constraints
    op.create_foreign_key(
        "fk_student_parent_id", "Student", "Parent", ["parent_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_student_institute_id", "Student", "Institute", ["institute_id"], ["id"]
    )

    # Drop old Supabase RLS policies that reference user_id
    # (must be done before dropping the column they depend on)
    op.execute('DROP POLICY IF EXISTS "users can only read there own data" ON "Student"')
    op.execute('DROP POLICY IF EXISTS "users can only insert there data" ON "Student"')
    op.execute('DROP POLICY IF EXISTS "user can only update there own data" ON "Student"')

    # Remove the old auth columns (now on Parent)
    op.drop_constraint("Student_user_id_key", "Student", type_="unique")
    op.drop_constraint("Student_phone_number_key", "Student", type_="unique")
    op.drop_column("Student", "user_id")
    op.drop_column("Student", "phone_number")

    # Add new RLS policies using parent_id → Parent.user_id
    op.execute("""
        CREATE POLICY "students can only read their own data"
        ON "Student" FOR SELECT
        USING (auth.uid() = (SELECT user_id FROM "Parent" WHERE id = parent_id))
    """)
    op.execute("""
        CREATE POLICY "students can only insert their own data"
        ON "Student" FOR INSERT
        WITH CHECK (auth.uid() = (SELECT user_id FROM "Parent" WHERE id = parent_id))
    """)
    op.execute("""
        CREATE POLICY "students can only update their own data"
        ON "Student" FOR UPDATE
        USING  (auth.uid() = (SELECT user_id FROM "Parent" WHERE id = parent_id))
        WITH CHECK (auth.uid() = (SELECT user_id FROM "Parent" WHERE id = parent_id))
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop new parent_id-based RLS policies
    op.execute('DROP POLICY IF EXISTS "students can only read their own data" ON "Student"')
    op.execute('DROP POLICY IF EXISTS "students can only insert their own data" ON "Student"')
    op.execute('DROP POLICY IF EXISTS "students can only update their own data" ON "Student"')

    # Restore phone_number and user_id on Student
    op.add_column(
        "Student",
        sa.Column("phone_number", sa.String(), nullable=True),
    )
    op.add_column(
        "Student",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.create_unique_constraint("Student_phone_number_key", "Student", ["phone_number"])
    op.create_unique_constraint("Student_user_id_key", "Student", ["user_id"])

    # Drop FK constraints and new columns from Student
    op.drop_constraint("fk_student_parent_id", "Student", type_="foreignkey")
    op.drop_constraint("fk_student_institute_id", "Student", type_="foreignkey")
    op.drop_column("Student", "parent_id")
    op.drop_column("Student", "institute_id")

    # Drop Parent table
    op.drop_index(op.f("ix_Parent_id"), table_name="Parent")
    op.drop_table("Parent")

    # Drop Institute table
    op.drop_index(op.f("ix_Institute_id"), table_name="Institute")
    op.drop_table("Institute")

    # Restore original user_id-based RLS policies
    op.execute("""
        CREATE POLICY "users can only read there own data"
        ON "Student" FOR SELECT
        USING (auth.uid() = user_id)
    """)
    op.execute("""
        CREATE POLICY "users can only insert there data"
        ON "Student" FOR INSERT
        WITH CHECK (auth.uid() = user_id)
    """)
    op.execute("""
        CREATE POLICY "user can only update there own data"
        ON "Student" FOR UPDATE
        USING  (auth.uid() = user_id)
        WITH CHECK (auth.uid() = user_id)
    """)
