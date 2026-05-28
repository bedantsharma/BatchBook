from datetime import date, datetime, time

from pydantic import BaseModel

from models.batch_base import BatchStatus


class BatchResponse(BaseModel):
    id: int
    institute_id: int
    name: str
    subject: str
    grade: str | None
    start_time: time
    end_time: time
    days_of_week: list[str]
    max_capacity: int
    start_date: date
    end_date: date
    status: BatchStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class BatchTeacherResponse(BaseModel):
    id: int
    batch_id: int
    teacher_id: int

    model_config = {"from_attributes": True}
