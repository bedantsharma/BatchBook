from pydantic import BaseModel, Field


class AssignTeacherRequest(BaseModel):
    teacher_id: int = Field(..., ge=1)
