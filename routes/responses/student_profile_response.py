from datetime import datetime

from pydantic import BaseModel

from DTO.student_model import StudentFeesStatus


class StudentProfileResponse(BaseModel):
    id: int
    name: str | None
    email: str | None
    fees_status: StudentFeesStatus
    parent_id: int | None
    institute_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
