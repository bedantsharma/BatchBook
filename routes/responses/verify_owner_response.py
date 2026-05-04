from pydantic import BaseModel, Field


class VerifyOwnerResponse(BaseModel):
    auth_token: str = Field(min_length=10)
    aud: str = Field(...)
    teacher_id: str = Field(...)
