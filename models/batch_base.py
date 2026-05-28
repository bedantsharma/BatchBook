import enum
from datetime import date, datetime, time

from sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Integer, JSON, String, Time

from db.base import Base


class BatchStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSING = "CLOSING"
    ARCHIVED = "ARCHIVED"


class BatchSchema(Base):
    __tablename__ = "Batch"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    institute_id = Column(Integer, ForeignKey("Institute.id"), nullable=False)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    grade = Column(String, nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    # JSON array of day strings, e.g. ["MON", "WED", "FRI"]
    days_of_week = Column(JSON, nullable=False)
    max_capacity = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False, default=date.today)
    end_date = Column(Date, nullable=False)
    status = Column(Enum(BatchStatus), nullable=False, default=BatchStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
