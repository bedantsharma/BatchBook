from pydantic import BaseModel, Field


class InviteTeacherRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
