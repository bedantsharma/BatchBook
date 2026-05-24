from pydantic import BaseModel, Field


class TeacherVerifyOtpRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
    token: str
