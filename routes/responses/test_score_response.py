from datetime import date, datetime

from pydantic import BaseModel, computed_field


class TestScoreResponse(BaseModel):
    id: int
    enrollment_id: int
    test_name: str
    subject: str
    date: date
    max_marks: int
    obtained_marks: int
    created_at: datetime

    @computed_field
    @property
    def percentage(self) -> float:
        return round((self.obtained_marks / self.max_marks) * 100, 1)

    model_config = {"from_attributes": True}


class StudentScoresResponse(BaseModel):
    enrollment_id: int
    scores: list[TestScoreResponse]
    needs_attention: bool
