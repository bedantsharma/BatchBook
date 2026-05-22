from pydantic import BaseModel


class CreateInstituteRequest(BaseModel):
    name: str
    city: str
