from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class InviteStudentRequest(BaseModel):
    student_name: str = Field(..., min_length=1, max_length=100)
    parent_phone: str = Field(..., description="10-digit Indian mobile number (no country code)")
    parent_name: str | None = None
    batch_id: int
    due_day: int = Field(default=None, ge=1, le=28)
    first_month_amount: Decimal | None = Field(default=None, ge=0)

    @field_validator("parent_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = v.strip().replace(" ", "").replace("-", "")
        if not digits.isdigit() or len(digits) != 10:
            raise ValueError("parent_phone must be a 10-digit Indian mobile number")
        return digits
