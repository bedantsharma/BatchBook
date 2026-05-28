from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.sql import expression

from db.base import Base


class EnrollmentSchema(Base):
    """Links a Student to a Batch.

    Each row represents one student enrolled in one batch.
    Fee records and attendance records are attached to this enrollment,
    not directly to the student — because a student in 2 batches has
    2 separate fee records and 2 attendance records.

    Design notes:
    - ``due_day`` is the student's personal fee due date (1–28), defaulting to
      the day they enrolled. Students joining mid-month each get their own cycle.
    - ``first_month_amount`` is the optional pro-rated fee for the joining month.
      If None, the batch's FeeStructure.monthly_amount is used instead.
    - Unique constraint on (student_id, batch_id) prevents double-enrollment.
    """

    __tablename__ = "Enrollment"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("Student.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("Batch.id"), nullable=False)
    enrolled_at = Column(DateTime, nullable=False, default=datetime.now)
    is_active = Column(Boolean, nullable=False, server_default=expression.true(), default=True)
    # Fee cycle: 1–28, defaults to the day of month when enrolled
    due_day = Column(Integer, nullable=False, default=1)
    # Pro-rated fee for the joining month; None → use FeeStructure.monthly_amount
    first_month_amount = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "batch_id", name="uq_enrollment_student_batch"),
    )
