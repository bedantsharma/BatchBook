from pydantic import BaseModel, Field


class VerifyUserResponse(BaseModel):
    auth_token: str = Field(min_length=10)
    refresh_token: str = Field(min_length=10)
    aud: str = Field(...)
    user_id: str = Field(...)
