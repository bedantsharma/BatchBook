from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class FeeStructureResponse(BaseModel):
    id: int
    batch_id: int
    monthly_amount: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}
