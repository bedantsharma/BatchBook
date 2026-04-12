from pydantic import BaseModel
from pydantic import Field

class OtpVerifyRequest(BaseModel):
    token: str
    phone: str = Field(min_length=10,max_length=10,pattern=r'^[6-9]\d{9}$')