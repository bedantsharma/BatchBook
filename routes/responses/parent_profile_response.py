from datetime import datetime

from pydantic import BaseModel


class StudentSummary(BaseModel):
    id: int
    name: str | None
    email: str | None
    fees_status: str
    institute_id: int | None

    model_config = {"from_attributes": True}


class ParentProfileResponse(BaseModel):
    id: int
    name: str | None
    phone_number: str
    created_at: datetime
    children: list[StudentSummary] = []

    model_config = {"from_attributes": True}
