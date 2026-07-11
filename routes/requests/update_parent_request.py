from pydantic import BaseModel, Field


class UpdateParentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z ]+$")
