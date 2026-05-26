from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class UpdateEnrollmentRequest(BaseModel):
    # At least one of these must be provided.
    due_day: int | None = Field(default=None, ge=1, le=28)
    first_month_amount: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateEnrollmentRequest":
        if self.due_day is None and self.first_month_amount is None:
            raise ValueError("At least one of due_day or first_month_amount must be provided")
        return self
