from pydantic import BaseModel


class InstituteQRResponse(BaseModel):
    join_code: str
    join_url: str
    institute_name: str
    owner_phone: str
