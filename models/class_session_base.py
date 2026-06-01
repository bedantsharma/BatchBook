from datetime import date, datetime, time

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Time

from db.base import Base


class ClassSessionSchema(Base):
    """One class held for a batch.

    Created by a teacher (or owner) when a session starts. Attendance rows
    are pre-populated for every active enrollment at creation time.
    """

    __tablename__ = "ClassSession"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("Batch.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    topic = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
