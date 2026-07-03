from datetime import date

from pydantic import BaseModel


class BackfillPaymentLinksResponse(BaseModel):
    month: date
    checked: int
    generated: int
    skipped_no_razorpay: int
    failed: int
    errors: list[dict]
