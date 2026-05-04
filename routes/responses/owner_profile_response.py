from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OwnerProfileResponse(BaseModel):
    id: int
    name: str | None
    phone_number: str
    email: str | None
    institute_name: str | None
    city: str | None
    teacher_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
