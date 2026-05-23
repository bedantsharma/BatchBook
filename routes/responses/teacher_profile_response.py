from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TeacherProfileResponse(BaseModel):
    id: int
    institute_id: int
    name: str
    phone_number: str
    user_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
