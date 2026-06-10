from decimal import Decimal

from pydantic import BaseModel


class OwnerStatsResponse(BaseModel):
    enrolled_students: int
    fees_collected_this_month: Decimal
    avg_attendance_this_month: float
