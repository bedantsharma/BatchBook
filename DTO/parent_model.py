from pydantic import BaseModel, Field


class Parent(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str = Field(min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
