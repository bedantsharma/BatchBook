from datetime import date

from pydantic import BaseModel, field_validator


class CreateTestScoreRequest(BaseModel):
    enrollment_id: int
    test_name: str
    subject: str
    date: date
    max_marks: int
    obtained_marks: int

    @field_validator("test_name", "subject")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()
