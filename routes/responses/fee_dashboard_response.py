from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from models.fee_record_base import FeeStatus


class FeeRecordSummary(BaseModel):
    id: int
    enrollment_id: int
    student_name: str
    batch_name: str
    month: date
    amount_due: Decimal
    amount_paid: Decimal
    status: FeeStatus
    paid_at: datetime | None
    payment_reference: str | None
    payment_link: str | None


class FeeDashboardResponse(BaseModel):
    total_due: Decimal
    total_collected: Decimal
    total_pending: Decimal
    collection_rate: float
    records: list[FeeRecordSummary]
