from enum import Enum

from pydantic import BaseModel, Field


class StudentFeesStatus(str, Enum):
    FULLY_PAID = "FULL_PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    NOT_PAID = "NOT_PAID"


class Student(BaseModel):
    name: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z ]+$")
    parent_id: int | None = None
    institute_id: int | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    fees_status: StudentFeesStatus = StudentFeesStatus.NOT_PAID
