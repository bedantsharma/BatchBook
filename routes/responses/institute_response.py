from datetime import datetime

from pydantic import BaseModel


class InstituteResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    city: str
    created_at: datetime

    model_config = {"from_attributes": True}
