from datetime import date, time

from pydantic import BaseModel, Field


_VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


class CreateBatchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    subject: str = Field(..., min_length=1, max_length=100)
    grade: str | None = Field(default=None, max_length=20)
    start_time: time
    end_time: time
    days_of_week: list[str] = Field(..., min_length=1)
    max_capacity: int = Field(..., ge=1)
    start_date: date | None = None
    end_date: date

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        invalid = [d for d in self.days_of_week if d.upper() not in _VALID_DAYS]
        if invalid:
            raise ValueError(f"Invalid days: {invalid}. Must be one of {sorted(_VALID_DAYS)}")
        self.days_of_week = [d.upper() for d in self.days_of_week]
