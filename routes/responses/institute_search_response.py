from pydantic import BaseModel, ConfigDict


class InstituteSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str
    join_code: str
    owner_name: str | None
