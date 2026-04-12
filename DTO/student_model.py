from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

class StudentFeesStatus(str, Enum):
    FULLY_PAID = "FULL_PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    NOT_PAID = "NOT_PAID"

class Student(BaseModel):
    name: str = Field(min_length=1, max_length=50, pattern=r'^[a-zA-Z ]+$')
    phone_number: str = Field(min_length=10,max_length=10,pattern=r'^\+?1?\d{9,15}$')
    fees_status: StudentFeesStatus  = StudentFeesStatus.NOT_PAID # paid or partial paid or not paid