from pydantic import BaseModel


class MarkAttendanceRequest(BaseModel):
    present_enrollment_ids: list[int]
