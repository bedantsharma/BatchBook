from pydantic import BaseModel


class GenerateSiteRequest(BaseModel):
    slug: str
    address: str
    phone_public: str
    email_public: str
    description: str
    course_fee_display: str
    color_scheme: str | None = None
