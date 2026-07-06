from pydantic import BaseModel


class PublicInstituteResponse(BaseModel):
    name: str
    city: str
    address: str | None
    phone_public: str | None
    email_public: str | None
    description: str | None
    course_fee_display: str | None
    color_scheme: str | None

    model_config = {"from_attributes": True}
