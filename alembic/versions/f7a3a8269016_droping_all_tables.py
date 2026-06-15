"""droping all tables

Revision ID: f7a3a8269016
Revises: 2530741662dc
Create Date: 2026-06-15 09:50:22.316606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f7a3a8269016'
down_revision: Union[str, Sequence[str], None] = '2530741662dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop order respects FK dependencies: child tables before the tables they reference.
    op.drop_index(op.f('ix_FeeRecord_id'), table_name='FeeRecord')
    op.drop_table('FeeRecord')
    op.drop_index(op.f('ix_TestScore_id'), table_name='TestScore')
    op.drop_table('TestScore')
    op.drop_index(op.f('ix_Attendance_id'), table_name='Attendance')
    op.drop_table('Attendance')
    op.drop_index(op.f('ix_BatchTeacher_id'), table_name='BatchTeacher')
    op.drop_table('BatchTeacher')
    op.drop_index(op.f('ix_FeeStructure_id'), table_name='FeeStructure')
    op.drop_table('FeeStructure')
    op.drop_index(op.f('ix_Enrollment_id'), table_name='Enrollment')
    op.drop_table('Enrollment')
    op.drop_index(op.f('ix_ClassSession_id'), table_name='ClassSession')
    op.drop_table('ClassSession')
    op.drop_index(op.f('ix_Teacher_id'), table_name='Teacher')
    op.drop_table('Teacher')
    op.drop_index(op.f('ix_Batch_id'), table_name='Batch')
    op.drop_table('Batch')
    op.drop_index(op.f('ix_Student_id'), table_name='Student')
    op.drop_table('Student')
    op.drop_index(op.f('ix_Parent_id'), table_name='Parent')
    op.drop_table('Parent')
    op.drop_index(op.f('ix_Institute_join_code'), table_name='Institute')
    op.drop_index(op.f('ix_Institute_id'), table_name='Institute')
    op.drop_table('Institute')
    op.drop_index(op.f('ix_Owner_id'), table_name='Owner')
    op.drop_table('Owner')


def downgrade() -> None:
    """Downgrade schema."""
    # Create order respects FK dependencies: referenced tables before the tables that reference them.
    op.create_table('Owner',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('phone_number', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('teacher_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('institute_name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('city', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('Owner_pkey')),
    sa.UniqueConstraint('phone_number', name=op.f('Owner_phone_number_key'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('teacher_id', name=op.f('Owner_teacher_id_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_Owner_id'), 'Owner', ['id'], unique=False)
    op.create_table('Institute',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('owner_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('city', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('join_code', sa.VARCHAR(length=8), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['Owner.id'], name=op.f('Institute_owner_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('Institute_pkey')),
    sa.UniqueConstraint('owner_id', name=op.f('Institute_owner_id_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_Institute_id'), 'Institute', ['id'], unique=False)
    op.create_index(op.f('ix_Institute_join_code'), 'Institute', ['join_code'], unique=True)
    op.create_table('Parent',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('phone_number', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('institute_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['institute_id'], ['Institute.id'], name=op.f('Parent_institute_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('Parent_pkey')),
    sa.UniqueConstraint('phone_number', name=op.f('Parent_phone_number_key'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('user_id', name=op.f('Parent_user_id_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_Parent_id'), 'Parent', ['id'], unique=False)
    op.create_table('Student',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fees_status', postgresql.ENUM('FULLY_PAID', 'PARTIALLY_PAID', 'NOT_PAID', name='studentfeesstatus'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('parent_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('institute_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['institute_id'], ['Institute.id'], name=op.f('fk_student_institute_id')),
    sa.ForeignKeyConstraint(['parent_id'], ['Parent.id'], name=op.f('fk_student_parent_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('Student_pkey'))
    )
    op.create_index(op.f('ix_Student_id'), 'Student', ['id'], unique=False)
    op.create_table('Batch',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institute_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('subject', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('grade', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('start_time', postgresql.TIME(), autoincrement=False, nullable=False),
    sa.Column('end_time', postgresql.TIME(), autoincrement=False, nullable=False),
    sa.Column('days_of_week', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('max_capacity', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('start_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('end_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('ACTIVE', 'CLOSING', 'ARCHIVED', name='batchstatus'), server_default=sa.text("'ACTIVE'::batchstatus"), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['institute_id'], ['Institute.id'], name=op.f('Batch_institute_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('Batch_pkey'))
    )
    op.create_index(op.f('ix_Batch_id'), 'Batch', ['id'], unique=False)
    op.create_table('Teacher',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institute_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('phone_number', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['institute_id'], ['Institute.id'], name=op.f('Teacher_institute_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('Teacher_pkey')),
    sa.UniqueConstraint('phone_number', name=op.f('Teacher_phone_number_key'), postgresql_include=[], postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('user_id', name=op.f('Teacher_user_id_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_Teacher_id'), 'Teacher', ['id'], unique=False)
    op.create_table('ClassSession',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('start_time', postgresql.TIME(), autoincrement=False, nullable=False),
    sa.Column('end_time', postgresql.TIME(), autoincrement=False, nullable=False),
    sa.Column('topic', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['Batch.id'], name=op.f('fk_class_session_batch_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('ClassSession_pkey'))
    )
    op.create_index(op.f('ix_ClassSession_id'), 'ClassSession', ['id'], unique=False)
    op.create_table('Enrollment',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('student_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('enrolled_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('due_day', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('first_month_amount', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['Batch.id'], name=op.f('fk_enrollment_batch_id')),
    sa.ForeignKeyConstraint(['student_id'], ['Student.id'], name=op.f('fk_enrollment_student_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('Enrollment_pkey')),
    sa.UniqueConstraint('student_id', 'batch_id', name=op.f('uq_enrollment_student_batch'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_Enrollment_id'), 'Enrollment', ['id'], unique=False)
    op.create_table('FeeStructure',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('monthly_amount', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['Batch.id'], name=op.f('fk_fee_structure_batch_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('FeeStructure_pkey')),
    sa.UniqueConstraint('batch_id', name=op.f('uq_fee_structure_batch'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_FeeStructure_id'), 'FeeStructure', ['id'], unique=False)
    op.create_table('BatchTeacher',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('batch_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('teacher_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['Batch.id'], name=op.f('BatchTeacher_batch_id_fkey')),
    sa.ForeignKeyConstraint(['teacher_id'], ['Teacher.id'], name=op.f('BatchTeacher_teacher_id_fkey')),
    sa.PrimaryKeyConstraint('id', name=op.f('BatchTeacher_pkey')),
    sa.UniqueConstraint('batch_id', 'teacher_id', name=op.f('uq_batch_teacher'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_BatchTeacher_id'), 'BatchTeacher', ['id'], unique=False)
    op.create_table('Attendance',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('enrollment_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('PRESENT', 'ABSENT', 'LATE', name='attendancestatus'), autoincrement=False, nullable=False),
    sa.Column('marked_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['enrollment_id'], ['Enrollment.id'], name=op.f('fk_attendance_enrollment_id')),
    sa.ForeignKeyConstraint(['session_id'], ['ClassSession.id'], name=op.f('fk_attendance_session_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('Attendance_pkey')),
    sa.UniqueConstraint('session_id', 'enrollment_id', name=op.f('uq_attendance_session_enrollment'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_Attendance_id'), 'Attendance', ['id'], unique=False)
    op.create_table('TestScore',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('enrollment_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('test_name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('subject', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('max_marks', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('obtained_marks', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['enrollment_id'], ['Enrollment.id'], name=op.f('fk_test_score_enrollment_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('TestScore_pkey'))
    )
    op.create_index(op.f('ix_TestScore_id'), 'TestScore', ['id'], unique=False)
    op.create_table('FeeRecord',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('enrollment_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('month', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('amount_due', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=False),
    sa.Column('amount_paid', sa.NUMERIC(precision=10, scale=2), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('NOT_PAID', 'PARTIALLY_PAID', 'FULLY_PAID', name='feestatus'), autoincrement=False, nullable=False),
    sa.Column('paid_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('payment_reference', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('payment_link', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['enrollment_id'], ['Enrollment.id'], name=op.f('fk_fee_record_enrollment_id')),
    sa.PrimaryKeyConstraint('id', name=op.f('FeeRecord_pkey')),
    sa.UniqueConstraint('enrollment_id', 'month', name=op.f('uq_fee_record_enrollment_month'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_FeeRecord_id'), 'FeeRecord', ['id'], unique=False)
