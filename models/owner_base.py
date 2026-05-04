from datetime import datetime

from sqlalchemy import UUID, Column, DateTime, Integer, String

from db.base import Base


class OwnerSchema(Base):
    __tablename__ = "Owner"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=True)
    phone_number = Column(String, unique=True, nullable=False)
    teacher_id = Column(UUID(as_uuid=True), unique=True, nullable=False)
    email = Column(String, nullable=True)
    institute_name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
