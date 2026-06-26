from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Index, Integer, String

from db.base import Base


class NotificationType(str, PyEnum):
    FEE_REMINDER = "FEE_REMINDER"
    FEE_RECEIPT = "FEE_RECEIPT"
    ABSENCE = "ABSENCE"
    ENROLLMENT_INVITE = "ENROLLMENT_INVITE"


class NotificationStatus(str, PyEnum):
    SENT = "SENT"
    SKIPPED_UNVERIFIED = "SKIPPED_UNVERIFIED"
    FAILED = "FAILED"


class NotificationSchema(Base):
    __tablename__ = "Notification"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    parent_id = Column(Integer, ForeignKey("Parent.id"), nullable=True)
    student_id = Column(Integer, ForeignKey("Student.id"), nullable=True)
    institute_id = Column(Integer, ForeignKey("Institute.id"), nullable=True)
    type = Column(Enum(NotificationType), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False)
    reason = Column(String, nullable=True)
    meta_data = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        Index("ix_notification_institute_id", "institute_id"),
        Index("ix_notification_student_id", "student_id"),
    )
