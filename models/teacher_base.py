from datetime import datetime

from sqlalchemy import UUID, Column, DateTime, ForeignKey, Integer, String

from db.base import Base


class TeacherSchema(Base):
    __tablename__ = "Teacher"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    institute_id = Column(Integer, ForeignKey("Institute.id"), nullable=False)
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
