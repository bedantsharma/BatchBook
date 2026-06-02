from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PaymentLinkResponse(BaseModel):
    record_id: int
    payment_link: str
    amount_pending: Decimal
    month: date
