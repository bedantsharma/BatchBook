from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String

from db.base import Base


class ScoreSchema(Base):
    __tablename__ = "TestScore"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    enrollment_id = Column(Integer, ForeignKey("Enrollment.id"), nullable=False)
    test_name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    max_marks = Column(Integer, nullable=False)
    obtained_marks = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
