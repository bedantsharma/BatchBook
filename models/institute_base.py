from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from db.base import Base


class InstituteSchema(Base):
    __tablename__ = "Institute"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("Owner.id"), unique=True, nullable=False)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
