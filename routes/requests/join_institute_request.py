from pydantic import BaseModel, Field


class JoinInstituteRequest(BaseModel):
    join_code: str = Field(..., min_length=6, max_length=8, description="Institute join code from QR or owner")
