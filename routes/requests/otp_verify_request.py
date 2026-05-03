from pydantic import BaseModel, Field


class OtpVerifyRequest(BaseModel):
    token: str
    phone: str = Field(min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
    name: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[a-zA-Z ]+$")
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
