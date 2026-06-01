from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from models.fee_record_base import FeeStatus


class FeeRecordResponse(BaseModel):
    id: int
    enrollment_id: int
    month: date
    amount_due: Decimal
    amount_paid: Decimal
    status: FeeStatus
    paid_at: datetime | None
    payment_reference: str | None
    payment_link: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
