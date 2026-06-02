from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel

from models.fee_record_base import FeeStatus


class StudentAttendanceItem(BaseModel):
    enrollment_id: int
    batch_id: int
    batch_name: str
    subject: str
    present: int
    total: int
    percentage: float


class StudentFeeItem(BaseModel):
    enrollment_id: int
    batch_id: int
    batch_name: str
    subject: str
    month: date
    amount_due: Decimal
    amount_paid: Decimal
    status: FeeStatus
    paid_at: datetime | None
    payment_reference: str | None
    payment_link: str | None


class StudentScheduleItem(BaseModel):
    session_id: int
    batch_id: int
    batch_name: str
    subject: str
    date: date
    start_time: time
    end_time: time
    topic: str | None
    attendance_status: str | None


class StudentUpcomingEventItem(BaseModel):
    session_id: int
    batch_id: int
    batch_name: str
    subject: str
    date: date
    start_time: time
    end_time: time
    topic: str | None
