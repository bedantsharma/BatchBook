from datetime import date, time

from sqlalchemy.ext.asyncio import AsyncSession

from models.attendance_base import AttendanceSchema, AttendanceStatus
from models.class_session_base import ClassSessionSchema
from repositories.attendance_repository import AttendanceRepository
from repositories.enrollment_repository import EnrollmentRepository


class AttendanceService:
    def __init__(self) -> None:
        self.attendance_repo = AttendanceRepository()
        self.enrollment_repo = EnrollmentRepository()

    async def create_session(
        self,
        db: AsyncSession,
        batch_id: int,
        session_date: date,
        start_time: time,
        end_time: time,
        topic: str | None = None,
    ) -> ClassSessionSchema:
        """Create a ClassSession and pre-populate one ABSENT Attendance row per active enrollment.

        Raises ValueError if a session already exists for this batch + date.
        """
        existing = await self.attendance_repo.get_session_by_batch_and_date(
            db, batch_id, session_date
        )
        if existing:
            raise ValueError(
                f"A session for batch {batch_id} on {session_date} already exists "
                f"(session_id={existing.id})"
            )

        session = ClassSessionSchema(
            batch_id=batch_id,
            date=session_date,
            start_time=start_time,
            end_time=end_time,
            topic=topic,
        )
        session = await self.attendance_repo.create_session(db, session)

        active_enrollments = await self.enrollment_repo.get_active_by_batch_id(db, batch_id)
        enrollment_ids = [e.id for e in active_enrollments]
        if enrollment_ids:
            await self.attendance_repo.bulk_create_absent(db, session.id, enrollment_ids)

        return session

    async def bulk_mark(
        self,
        db: AsyncSession,
        session_id: int,
        present_enrollment_ids: list[int],
    ) -> list[AttendanceSchema]:
        """Set given enrollments to PRESENT; all others in the session stay ABSENT.

        Returns the full attendance list for the session after marking.
        Raises ValueError if the session does not exist.
        """
        session = await self.attendance_repo.get_session_by_id(db, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        rows = await self.attendance_repo.get_by_session(db, session_id)
        present_set = set(present_enrollment_ids)

        for row in rows:
            target_status = (
                AttendanceStatus.PRESENT
                if row.enrollment_id in present_set
                else AttendanceStatus.ABSENT
            )
            if row.status != target_status:
                await self.attendance_repo.update_status(db, row, target_status)

        return await self.attendance_repo.get_by_session(db, session_id)

    async def get_session_attendance(
        self, db: AsyncSession, session_id: int
    ) -> list[AttendanceSchema]:
        """Return all attendance rows for a session.

        Raises ValueError if the session does not exist.
        """
        session = await self.attendance_repo.get_session_by_id(db, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        return await self.attendance_repo.get_by_session(db, session_id)

    async def get_batch_sessions(
        self, db: AsyncSession, batch_id: int
    ) -> list[ClassSessionSchema]:
        """Return all sessions for a batch, ordered by date descending."""
        return await self.attendance_repo.get_sessions_by_batch(db, batch_id)

    async def get_student_attendance_summary(
        self, db: AsyncSession, enrollment_id: int, month_str: str
    ) -> dict:
        """Return { present, total, percentage } for an enrollment in a given month.

        month_str: "YYYY-MM"
        """
        from datetime import datetime

        year, month = (int(p) for p in month_str.split("-"))
        start = date(year, month, 1)
        # last day of month
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)

        # Get all sessions in this month for the enrollment's batch
        enrollment = await self.enrollment_repo.get_by_id(db, enrollment_id)
        if not enrollment:
            raise ValueError(f"Enrollment {enrollment_id} not found")

        all_sessions = await self.attendance_repo.get_sessions_by_batch(db, enrollment.batch_id)
        month_sessions = [s for s in all_sessions if start <= s.date < end]
        session_ids = [s.id for s in month_sessions]

        attendance_rows = await self.attendance_repo.get_by_enrollment_in_sessions(
            db, enrollment_id, session_ids
        )

        total = len(attendance_rows)
        present = sum(1 for row in attendance_rows if row.status == AttendanceStatus.PRESENT)
        percentage = round(present / total * 100, 1) if total > 0 else 0.0

        return {"present": present, "total": total, "percentage": percentage}


def get_attendance_service() -> AttendanceService:
    return AttendanceService()
