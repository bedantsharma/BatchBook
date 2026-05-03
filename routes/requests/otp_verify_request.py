from typing import Optional
from pydantic import BaseModel, Field

class OtpVerifyRequest(BaseModel):
    token: str
    phone: str = Field(min_length=10, max_length=10, pattern=r'^[6-9]\d{9}$')
    name: Optional[str] = Field(default=None, min_length=1, max_length=50, pattern=r'^[a-zA-Z ]+$')
    email: Optional[str] = Field(default=None, pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')