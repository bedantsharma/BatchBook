from decimal import Decimal

from pydantic import BaseModel, Field


class MarkPaymentRequest(BaseModel):
    amount_paid: Decimal = Field(..., ge=0, decimal_places=2)
    reference: str | None = Field(default=None, max_length=255)
