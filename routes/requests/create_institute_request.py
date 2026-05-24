from pydantic import BaseModel, Field


class CreateInstituteRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
