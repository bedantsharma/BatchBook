from pydantic import BaseModel, Field

class OtpGenerateRequest(BaseModel):
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
