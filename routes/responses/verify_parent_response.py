from pydantic import BaseModel, Field


class StudentSummaryInToken(BaseModel):
    id: int
    name: str | None
    fees_status: str

    model_config = {"from_attributes": True}


class VerifyParentResponse(BaseModel):
    auth_token: str = Field(min_length=10)
    refresh_token: str = Field(min_length=10)
    aud: str = Field(...)
    user_id: str = Field(...)
    children: list[StudentSummaryInToken] = []
