from decimal import Decimal

from pydantic import BaseModel, Field


class SetupFeeStructureRequest(BaseModel):
    batch_id: int = Field(..., gt=0)
    monthly_amount: Decimal = Field(..., gt=0, decimal_places=2)
