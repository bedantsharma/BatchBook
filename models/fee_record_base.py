import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from db.base import Base


class FeeStatus(str, enum.Enum):
    NOT_PAID = "NOT_PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    FULLY_PAID = "FULLY_PAID"


class FeeRecordSchema(Base):
    """One fee record per student (enrollment) per month.

    Unique constraint on (enrollment_id, month) prevents duplicate records.
    month is stored as the first day of the month, e.g. 2026-05-01.
    """

    __tablename__ = "FeeRecord"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    enrollment_id = Column(Integer, ForeignKey("Enrollment.id"), nullable=False)
    month = Column(Date, nullable=False)
    amount_due = Column(Numeric(10, 2), nullable=False)
    amount_paid = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(Enum(FeeStatus), nullable=False, default=FeeStatus.NOT_PAID)
    paid_at = Column(DateTime, nullable=True)
    payment_reference = Column(String, nullable=True)
    payment_link = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("enrollment_id", "month", name="uq_fee_record_enrollment_month"),
    )
