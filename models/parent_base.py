from datetime import datetime

from sqlalchemy import UUID, Column, DateTime, ForeignKey, Integer, String

from db.base import Base


class ParentSchema(Base):
    __tablename__ = "Parent"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=True)
    phone_number = Column(String, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=True)
    institute_id = Column(Integer, ForeignKey("Institute.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
