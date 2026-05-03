from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from DTO.student_model import StudentFeesStatus


class StudentProfileResponse(BaseModel):
    id: int
    name: str | None
    phone_number: str
    email: str | None
    fees_status: StudentFeesStatus
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
