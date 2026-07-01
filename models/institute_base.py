import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String

from db.base import Base


class RazorpayStatus(str, enum.Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTED = "CONNECTED"
    NEEDS_RECONNECT = "NEEDS_RECONNECT"


class InstituteSchema(Base):
    __tablename__ = "Institute"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("Owner.id"), nullable=False, unique=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    join_code = Column(String(8), nullable=False, unique=True, index=True)
    razorpay_key_id = Column(String, nullable=True)
    razorpay_key_secret_encrypted = Column(String, nullable=True)
    razorpay_status = Column(Enum(RazorpayStatus), nullable=False, default=RazorpayStatus.NOT_CONNECTED)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
