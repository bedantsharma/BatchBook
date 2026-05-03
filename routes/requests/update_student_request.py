from typing import Optional
from pydantic import BaseModel, Field
from DTO.student_model import StudentFeesStatus

class UpdateStudentRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50, pattern=r'^[a-zA-Z ]+$')
    email: Optional[str] = Field(default=None, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    fees_status: Optional[StudentFeesStatus] = None