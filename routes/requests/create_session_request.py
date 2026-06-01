from datetime import date, time

from pydantic import BaseModel, Field, model_validator


class CreateSessionRequest(BaseModel):
    batch_id: int
    date: date
    start_time: time
    end_time: time
    topic: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def end_after_start(self) -> "CreateSessionRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self
