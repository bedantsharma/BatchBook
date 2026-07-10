from pydantic import BaseModel


class SeedDemoAccountsResponse(BaseModel):
    owner_created: bool
    institute_created: bool
    batches_created: list[str]
    student_created: bool
    sessions_created: int
    fee_records_created: int
