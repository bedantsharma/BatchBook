from datetime import date, datetime, time

from pydantic import BaseModel

from models.attendance_base import AttendanceStatus


class ClassSessionResponse(BaseModel):
    id: int
    batch_id: int
    date: date
    start_time: time
    end_time: time
    topic: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AttendanceResponse(BaseModel):
    id: int
    session_id: int
    enrollment_id: int
    status: AttendanceStatus
    marked_at: datetime

    model_config = {"from_attributes": True}


class StudentAttendanceSummaryResponse(BaseModel):
    present: int
    total: int
    percentage: float
