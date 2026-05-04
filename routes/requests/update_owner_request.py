from pydantic import BaseModel, Field


class UpdateOwnerRequest(BaseModel):
    name: str | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    institute_name: str | None = None
    city: str | None = None
