from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CreateEnrollmentRequest(BaseModel):
    student_id: int = Field(..., gt=0)
    batch_id: int = Field(..., gt=0)
    # Fee due day of month: 1–28. If omitted, defaults to today's day-of-month.
    due_day: int | None = Field(default=None, ge=1, le=28)
    # Pro-rated fee for the joining month. If omitted, FeeStructure.monthly_amount is used.
    first_month_amount: Decimal | None = Field(default=None, gt=0)
