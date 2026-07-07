from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.attendance_base import AttendanceSchema, AttendanceStatus
from models.class_session_base import ClassSessionSchema


class AttendanceRepository:
    # ─── ClassSession ──────────────────────────────────────────────────────────

    async def create_session(
        self, db: AsyncSession, session: ClassSessionSchema
    ) -> ClassSessionSchema:
        """Insert a ClassSession, relying on the DB's uq_class_session_batch_date
        constraint as the source of truth for duplicate detection — the
        caller's pre-check (get_session_by_batch_and_date) is only an
        optimization and is not race-safe on its own (two concurrent/retried
        requests can both pass it before either commits).
        """
        db.add(session)
        try:
            await db.commit()
        except IntegrityError as e:
            await db.rollback()
            raise ValueError(
                f"A session for batch {session.batch_id} on {session.date} already exists"
            ) from e
        await db.refresh(session)
        return session

    async def get_session_by_id(
        self, db: AsyncSession, session_id: int
    ) -> ClassSessionSchema | None:
        result = await db.execute(
            select(ClassSessionSchema).where(ClassSessionSchema.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_sessions_by_batch(
        self, db: AsyncSession, batch_id: int
    ) -> list[ClassSessionSchema]:
        result = await db.execute(
            select(ClassSessionSchema)
            .where(ClassSessionSchema.batch_id == batch_id)
            .order_by(ClassSessionSchema.date.desc())
        )
        return list(result.scalars().all())

    async def get_session_by_batch_and_date(
        self, db: AsyncSession, batch_id: int, session_date: date
    ) -> ClassSessionSchema | None:
        result = await db.execute(
            select(ClassSessionSchema).where(
                ClassSessionSchema.batch_id == batch_id,
                ClassSessionSchema.date == session_date,
            )
        )
        return result.scalar_one_or_none()

    # ─── Attendance ────────────────────────────────────────────────────────────

    async def bulk_create_absent(
        self, db: AsyncSession, session_id: int, enrollment_ids: list[int]
    ) -> list[AttendanceSchema]:
        rows = [
            AttendanceSchema(
                session_id=session_id,
                enrollment_id=eid,
                status=AttendanceStatus.ABSENT,
            )
            for eid in enrollment_ids
        ]
        db.add_all(rows)
        await db.commit()
        for row in rows:
            await db.refresh(row)
        return rows

    async def get_by_session(
        self, db: AsyncSession, session_id: int
    ) -> list[AttendanceSchema]:
        result = await db.execute(
            select(AttendanceSchema).where(AttendanceSchema.session_id == session_id)
        )
        return list(result.scalars().all())

    async def get_by_session_and_enrollment(
        self, db: AsyncSession, session_id: int, enrollment_id: int
    ) -> AttendanceSchema | None:
        result = await db.execute(
            select(AttendanceSchema).where(
                AttendanceSchema.session_id == session_id,
                AttendanceSchema.enrollment_id == enrollment_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        db: AsyncSession,
        attendance: AttendanceSchema,
        status: AttendanceStatus,
    ) -> AttendanceSchema:
        attendance.status = status
        await db.commit()
        await db.refresh(attendance)
        return attendance

    async def get_by_enrollment_in_sessions(
        self, db: AsyncSession, enrollment_id: int, session_ids: list[int]
    ) -> list[AttendanceSchema]:
        if not session_ids:
            return []
        result = await db.execute(
            select(AttendanceSchema).where(
                AttendanceSchema.enrollment_id == enrollment_id,
                AttendanceSchema.session_id.in_(session_ids),
            )
        )
        return list(result.scalars().all())
