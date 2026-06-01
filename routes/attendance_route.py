from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from models.batch_base import BatchSchema
from routes.requests.create_session_request import CreateSessionRequest
from routes.requests.mark_attendance_request import MarkAttendanceRequest
from routes.responses.attendance_response import (
    AttendanceResponse,
    ClassSessionResponse,
    StudentAttendanceSummaryResponse,
)
from services.attendance_service import AttendanceService, get_attendance_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service

router = APIRouter(prefix="/attendance")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
AttendanceServiceDep = Annotated[AttendanceService, Depends(get_attendance_service)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


async def _get_current_owner_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    try:
        return await owner_service.get_current_teacher_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _get_institute_id(
    db: AsyncSession,
    owner_user_id: UUID,
    owner_service: OwnerService,
    institute_service: InstituteService,
) -> int:
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=owner_user_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    institute = await institute_service.get_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(
            status_code=404,
            detail="Institute not set up yet — please create an institute first",
        )
    return institute.id


async def _verify_batch_belongs_to_institute(
    db: AsyncSession, batch_id: int, institute_id: int
) -> None:
    result = await db.execute(select(BatchSchema).where(BatchSchema.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.institute_id != institute_id:
        raise HTTPException(status_code=403, detail="Batch does not belong to your institute")


# ─── POST /attendance/session ─────────────────────────────────────────────────

@router.post(
    "/session",
    summary="Create a class session and pre-populate absent attendance for all active enrollments",
    response_model=ClassSessionResponse,
    status_code=201,
)
async def create_session(
    request: CreateSessionRequest,
    attendance_service: AttendanceServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    """Create a class session.

    On creation, one Attendance row is pre-inserted for every active enrollment
    in the batch with status=ABSENT. Use POST /session/{id}/mark to flip present students.

    Returns 409 if a session for this batch+date already exists.
    """
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    await _verify_batch_belongs_to_institute(db, request.batch_id, institute_id)

    try:
        session = await attendance_service.create_session(
            db=db,
            batch_id=request.batch_id,
            session_date=request.date,
            start_time=request.start_time,
            end_time=request.end_time,
            topic=request.topic,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to create session")

    return session


# ─── POST /attendance/session/{session_id}/mark ────────────────────────────────

@router.post(
    "/session/{session_id}/mark",
    summary="Mark attendance: supply present enrollment IDs; all others stay absent",
    response_model=list[AttendanceResponse],
)
async def mark_attendance(
    session_id: int,
    request: MarkAttendanceRequest,
    attendance_service: AttendanceServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    """Mark attendance for a session.

    Provide the list of ``enrollment_id`` values for students who were PRESENT.
    Every enrolled student not in that list is marked ABSENT.
    Can be called multiple times — it overwrites previous marks.
    """
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)

    # Verify the session's batch belongs to this institute
    session = await attendance_service.attendance_repo.get_session_by_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await _verify_batch_belongs_to_institute(db, session.batch_id, institute_id)

    try:
        return await attendance_service.bulk_mark(
            db=db,
            session_id=session_id,
            present_enrollment_ids=request.present_enrollment_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to mark attendance")


# ─── GET /attendance/session/{session_id} ─────────────────────────────────────

@router.get(
    "/session/{session_id}",
    summary="Get full attendance for a session",
    response_model=list[AttendanceResponse],
)
async def get_session_attendance(
    session_id: int,
    attendance_service: AttendanceServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)

    session = await attendance_service.attendance_repo.get_session_by_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await _verify_batch_belongs_to_institute(db, session.batch_id, institute_id)

    try:
        return await attendance_service.get_session_attendance(db=db, session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── GET /attendance/batch/{batch_id} ─────────────────────────────────────────

@router.get(
    "/batch/{batch_id}",
    summary="List all sessions for a batch (ordered by date desc)",
    response_model=list[ClassSessionResponse],
)
async def list_batch_sessions(
    batch_id: int,
    attendance_service: AttendanceServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    await _verify_batch_belongs_to_institute(db, batch_id, institute_id)
    return await attendance_service.get_batch_sessions(db=db, batch_id=batch_id)


# ─── GET /attendance/student/{enrollment_id} ──────────────────────────────────

@router.get(
    "/student/{enrollment_id}",
    summary="Monthly attendance summary for one enrollment (present / total / %)",
    response_model=StudentAttendanceSummaryResponse,
)
async def get_student_attendance_summary(
    enrollment_id: int,
    month: str,
    attendance_service: AttendanceServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    """Query param ``month`` must be in YYYY-MM format (e.g. 2026-05)."""
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)

    from models.enrollment_base import EnrollmentSchema
    result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await _verify_batch_belongs_to_institute(db, enrollment.batch_id, institute_id)

    try:
        return await attendance_service.get_student_attendance_summary(
            db=db, enrollment_id=enrollment_id, month_str=month
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to fetch attendance summary")
