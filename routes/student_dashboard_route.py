from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from models.attendance_base import AttendanceStatus
from models.batch_base import BatchSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from repositories.attendance_repository import AttendanceRepository
from routes.responses.student_dashboard_response import (
    StudentAttendanceItem,
    StudentFeeItem,
    StudentScheduleItem,
    StudentUpcomingEventItem,
)
from services.parent_service import ParentService, get_parent_service

router = APIRouter(prefix="/student/me")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
ParentServiceDep = Annotated[ParentService, Depends(get_parent_service)]


async def _get_current_parent(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    parent_service: ParentServiceDep,
    db: AsyncSession = Depends(get_db),
) -> ParentSchema:
    try:
        user_id = await parent_service.get_current_user_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    parent = await parent_service.get_parent_by_user_id(db=db, user_id=user_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent record not found")
    return parent


async def _verify_student_belongs_to_parent(
    db: AsyncSession,
    student_id: int,
    parent: ParentSchema,
) -> StudentSchema:
    result = await db.execute(
        select(StudentSchema).where(
            StudentSchema.id == student_id,
            StudentSchema.parent_id == parent.id,
        )
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(
            status_code=403,
            detail="Student not found or does not belong to this parent",
        )
    return student


async def _get_active_enrollments_for_student(
    db: AsyncSession, student_id: int
) -> list[EnrollmentSchema]:
    result = await db.execute(
        select(EnrollmentSchema).where(
            EnrollmentSchema.student_id == student_id,
            EnrollmentSchema.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def _get_batch(db: AsyncSession, batch_id: int) -> BatchSchema:
    result = await db.execute(select(BatchSchema).where(BatchSchema.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    return batch


# ─── GET /student/me/attendance ───────────────────────────────────────────────


@router.get(
    "/attendance",
    summary="Monthly attendance summary for a student across all their batches",
    response_model=list[StudentAttendanceItem],
)
async def get_student_attendance(
    student_id: int = Query(..., description="The student's ID"),
    month: str = Query(..., description="Month in YYYY-MM format (e.g. 2026-05)"),
    db: AsyncSession = Depends(get_db),
    parent: ParentSchema = Depends(_get_current_parent),
):
    """Return per-batch attendance summary for a student for a given month.

    ``month`` must be in YYYY-MM format.  Only active enrollments are included.
    """
    await _verify_student_belongs_to_parent(db, student_id, parent)

    try:
        year, mon = (int(p) for p in month.split("-"))
        start = date(year, mon, 1)
        end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="month must be in YYYY-MM format")

    enrollments = await _get_active_enrollments_for_student(db, student_id)
    if not enrollments:
        return []

    attendance_repo = AttendanceRepository()
    items: list[StudentAttendanceItem] = []

    for enrollment in enrollments:
        batch = await _get_batch(db, enrollment.batch_id)
        all_sessions = await attendance_repo.get_sessions_by_batch(db, enrollment.batch_id)
        month_sessions = [s for s in all_sessions if start <= s.date < end]
        session_ids = [s.id for s in month_sessions]
        rows = await attendance_repo.get_by_enrollment_in_sessions(db, enrollment.id, session_ids)
        total = len(rows)
        present = sum(1 for r in rows if r.status == AttendanceStatus.PRESENT)
        percentage = round(present / total * 100, 1) if total > 0 else 0.0
        items.append(
            StudentAttendanceItem(
                enrollment_id=enrollment.id,
                batch_id=batch.id,
                batch_name=batch.name,
                subject=batch.subject,
                present=present,
                total=total,
                percentage=percentage,
            )
        )

    return items


# ─── GET /student/me/fee ──────────────────────────────────────────────────────


@router.get(
    "/fee",
    summary="Fee status for a student across all their batches for a given month",
    response_model=list[StudentFeeItem],
)
async def get_student_fee(
    student_id: int = Query(..., description="The student's ID"),
    month: str = Query(..., description="Month in YYYY-MM format (e.g. 2026-05)"),
    db: AsyncSession = Depends(get_db),
    parent: ParentSchema = Depends(_get_current_parent),
):
    """Return fee records for a student for the given month, one item per enrollment."""
    await _verify_student_belongs_to_parent(db, student_id, parent)

    try:
        parts = month.split("-")
        month_date = date(int(parts[0]), int(parts[1]), 1)
    except (ValueError, TypeError, IndexError):
        raise HTTPException(status_code=422, detail="month must be in YYYY-MM format")

    enrollments = await _get_active_enrollments_for_student(db, student_id)
    if not enrollments:
        return []

    items: list[StudentFeeItem] = []
    for enrollment in enrollments:
        batch = await _get_batch(db, enrollment.batch_id)
        result = await db.execute(
            select(FeeRecordSchema).where(
                FeeRecordSchema.enrollment_id == enrollment.id,
                FeeRecordSchema.month == month_date,
            )
        )
        fee_record = result.scalar_one_or_none()
        if fee_record is None:
            continue
        items.append(
            StudentFeeItem(
                enrollment_id=enrollment.id,
                batch_id=batch.id,
                batch_name=batch.name,
                subject=batch.subject,
                month=fee_record.month,
                amount_due=fee_record.amount_due,
                amount_paid=fee_record.amount_paid,
                status=fee_record.status,
                paid_at=fee_record.paid_at,
                payment_reference=fee_record.payment_reference,
                payment_link=fee_record.payment_link,
            )
        )

    return items


# ─── GET /student/me/schedule ─────────────────────────────────────────────────


@router.get(
    "/schedule",
    summary="Class sessions for a student on a given date",
    response_model=list[StudentScheduleItem],
)
async def get_student_schedule(
    student_id: int = Query(..., description="The student's ID"),
    date_str: str = Query(..., alias="date", description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
    parent: ParentSchema = Depends(_get_current_parent),
):
    """Return all class sessions the student has on a given date, with their attendance status."""
    await _verify_student_belongs_to_parent(db, student_id, parent)

    try:
        session_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be in YYYY-MM-DD format")

    enrollments = await _get_active_enrollments_for_student(db, student_id)
    if not enrollments:
        return []

    items: list[StudentScheduleItem] = []
    attendance_repo = AttendanceRepository()

    for enrollment in enrollments:
        batch = await _get_batch(db, enrollment.batch_id)
        session = await attendance_repo.get_session_by_batch_and_date(
            db, enrollment.batch_id, session_date
        )
        if session is None:
            continue

        att_row = await attendance_repo.get_by_session_and_enrollment(
            db, session.id, enrollment.id
        )
        att_status = att_row.status.value if att_row else None

        items.append(
            StudentScheduleItem(
                session_id=session.id,
                batch_id=batch.id,
                batch_name=batch.name,
                subject=batch.subject,
                date=session.date,
                start_time=session.start_time,
                end_time=session.end_time,
                topic=session.topic,
                attendance_status=att_status,
            )
        )

    items.sort(key=lambda x: x.start_time)
    return items


# ─── GET /student/me/upcoming-events ─────────────────────────────────────────


@router.get(
    "/upcoming-events",
    summary="Upcoming class sessions for a student across all their batches",
    response_model=list[StudentUpcomingEventItem],
)
async def get_student_upcoming_events(
    student_id: int = Query(..., description="The student's ID"),
    limit: int = Query(default=10, ge=1, le=50, description="Max number of events to return"),
    db: AsyncSession = Depends(get_db),
    parent: ParentSchema = Depends(_get_current_parent),
):
    """Return upcoming class sessions (from today onwards) across all batches, ordered by date."""
    await _verify_student_belongs_to_parent(db, student_id, parent)

    enrollments = await _get_active_enrollments_for_student(db, student_id)
    if not enrollments:
        return []

    today = datetime.now().date()
    all_upcoming: list[StudentUpcomingEventItem] = []
    attendance_repo = AttendanceRepository()

    for enrollment in enrollments:
        batch = await _get_batch(db, enrollment.batch_id)
        sessions = await attendance_repo.get_sessions_by_batch(db, enrollment.batch_id)
        for session in sessions:
            if session.date >= today:
                all_upcoming.append(
                    StudentUpcomingEventItem(
                        session_id=session.id,
                        batch_id=batch.id,
                        batch_name=batch.name,
                        subject=batch.subject,
                        date=session.date,
                        start_time=session.start_time,
                        end_time=session.end_time,
                        topic=session.topic,
                    )
                )

    all_upcoming.sort(key=lambda x: (x.date, x.start_time))
    return all_upcoming[:limit]
