from pydantic import BaseModel


class BackfillPaymentLinksRequest(BaseModel):
    institute_id: int | None = None
