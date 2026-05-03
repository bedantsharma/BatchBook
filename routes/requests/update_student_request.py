from pydantic import BaseModel, Field

from DTO.student_model import StudentFeesStatus


class UpdateStudentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[a-zA-Z ]+$")
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    fees_status: StudentFeesStatus | None = None
