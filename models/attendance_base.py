import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, UniqueConstraint

from db.base import Base


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    LATE = "LATE"


class AttendanceSchema(Base):
    """One attendance record per student per class session.

    Pre-created as ABSENT when a session opens; updated to PRESENT or LATE
    via bulk_mark.  Unique constraint prevents duplicate rows per session+enrollment.
    """

    __tablename__ = "Attendance"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("ClassSession.id"), nullable=False)
    enrollment_id = Column(Integer, ForeignKey("Enrollment.id"), nullable=False)
    status = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.ABSENT)
    marked_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "enrollment_id", name="uq_attendance_session_enrollment"),
    )
