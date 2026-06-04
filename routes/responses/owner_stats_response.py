from decimal import Decimal

from pydantic import BaseModel


class OwnerStatsResponse(BaseModel):
    students_enrolled: int
    fees_collected_this_month: Decimal
    avg_attendance_pct: float
