from datetime import date, time

from pydantic import BaseModel, Field


_VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


class UpdateBatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    grade: str | None = Field(default=None, max_length=20)
    start_time: time | None = None
    end_time: time | None = None
    days_of_week: list[str] | None = None
    max_capacity: int | None = Field(default=None, ge=1)
    end_date: date | None = None

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        if self.days_of_week is not None:
            invalid = [d for d in self.days_of_week if d.upper() not in _VALID_DAYS]
            if invalid:
                raise ValueError(f"Invalid days: {invalid}. Must be one of {sorted(_VALID_DAYS)}")
            self.days_of_week = [d.upper() for d in self.days_of_week]
