from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class EnrollmentResponse(BaseModel):
    id: int
    student_id: int
    batch_id: int
    enrolled_at: datetime
    is_active: bool
    due_day: int
    first_month_amount: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}
