from decimal import Decimal
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
from models.student_base import StudentSchema
from routes.requests.create_enrollment_request import CreateEnrollmentRequest
from routes.requests.update_enrollment_request import UpdateEnrollmentRequest
from routes.responses.enrollment_response import EnrollmentResponse
from services.enrollment_service import EnrollmentService, get_enrollment_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service

router = APIRouter(prefix="/enrollment")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
EnrollmentServiceDep = Annotated[EnrollmentService, Depends(get_enrollment_service)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


# ─── Auth helpers ─────────────────────────────────────────────────────────────


async def _get_current_owner_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    """Validate the JWT and return the owner's Supabase user UUID."""
    try:
        return await owner_service.get_current_teacher_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _resolve_institute_id(
    db: AsyncSession,
    owner_user_id: UUID,
    owner_service: OwnerService,
    institute_service: InstituteService,
) -> int:
    """Resolve owner JWT → owner record → institute id.

    Raises 404 if the owner record or institute is missing.
    """
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
    """Raise 404 if the batch does not exist or does not belong to this institute."""
    result = await db.execute(
        select(BatchSchema).where(BatchSchema.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.institute_id != institute_id:
        raise HTTPException(
            status_code=403,
            detail="Batch does not belong to your institute",
        )


async def _verify_student_belongs_to_institute(
    db: AsyncSession, student_id: int, institute_id: int
) -> None:
    """Raise 404 if the student does not exist or does not belong to this institute."""
    result = await db.execute(
        select(StudentSchema).where(StudentSchema.id == student_id)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if student.institute_id != institute_id:
        raise HTTPException(
            status_code=403,
            detail="Student does not belong to your institute",
        )


# ─── POST /enrollment/ ────────────────────────────────────────────────────────


@router.post(
    "/",
    summary="Enroll a student in a batch",
    response_model=EnrollmentResponse,
    status_code=201,
)
async def enroll_student(
    request: CreateEnrollmentRequest,
    enrollment_service: EnrollmentServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Enroll a student in a batch.

    - ``due_day`` (1–28): the student's personal fee due day. Defaults to today's day-of-month.
    - ``first_month_amount``: pro-rated fee for the joining month. Omit to use the batch's
      standard monthly fee (FeeStructure.monthly_amount — set up separately).

    Returns 409 if the student is already actively enrolled in this batch.
    Returns 404 if the batch or student is not found in this institute.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_batch_belongs_to_institute(db, request.batch_id, institute_id)
    await _verify_student_belongs_to_institute(db, request.student_id, institute_id)

    try:
        enrollment = await enrollment_service.enroll_student(
            db=db,
            student_id=request.student_id,
            batch_id=request.batch_id,
            due_day=request.due_day,
            first_month_amount=request.first_month_amount,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to enroll student — check logs")

    return enrollment


# ─── GET /enrollment/batch/{batch_id} ────────────────────────────────────────


@router.get(
    "/batch/{batch_id}",
    summary="List all students enrolled in a batch",
    response_model=list[EnrollmentResponse],
)
async def list_enrollments_by_batch(
    batch_id: int,
    enrollment_service: EnrollmentServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Return all enrollments (active + inactive) for a batch."""
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_batch_belongs_to_institute(db, batch_id, institute_id)

    return await enrollment_service.get_enrollments_by_batch(db=db, batch_id=batch_id)


# ─── PATCH /enrollment/{enrollment_id} ────────────────────────────────────────


@router.patch(
    "/{enrollment_id}",
    summary="Update due_day or first_month_amount for an enrollment",
    response_model=EnrollmentResponse,
)
async def update_enrollment(
    enrollment_id: int,
    request: UpdateEnrollmentRequest,
    enrollment_service: EnrollmentServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Update the fee configuration of an enrollment.

    Useful when a teacher made a mistake in ``due_day`` or ``first_month_amount``
    at enrollment time.  At least one field must be provided.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )

    # Fetch enrollment first to verify batch ownership before mutating
    from models.enrollment_base import EnrollmentSchema
    result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == enrollment_id)
    )
    enrollment_check = result.scalar_one_or_none()
    if not enrollment_check:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await _verify_batch_belongs_to_institute(db, enrollment_check.batch_id, institute_id)

    try:
        enrollment = await enrollment_service.update_enrollment(
            db=db,
            enrollment_id=enrollment_id,
            due_day=request.due_day,
            first_month_amount=request.first_month_amount,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to update enrollment — check logs")

    return enrollment


# ─── DELETE /enrollment/{enrollment_id} ───────────────────────────────────────


@router.delete(
    "/{enrollment_id}",
    summary="Remove a student from a batch (soft-delete: sets is_active = False)",
    status_code=204,
)
async def remove_enrollment(
    enrollment_id: int,
    enrollment_service: EnrollmentServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Soft-delete an enrollment.

    Sets ``is_active = False`` so the historical record is preserved for fee
    and attendance reporting. The student can be re-enrolled in the same batch
    via a new POST /enrollment/ call.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )

    # Verify batch ownership before deletion
    from models.enrollment_base import EnrollmentSchema
    result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == enrollment_id)
    )
    enrollment_check = result.scalar_one_or_none()
    if not enrollment_check:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await _verify_batch_belongs_to_institute(db, enrollment_check.batch_id, institute_id)

    try:
        await enrollment_service.remove_enrollment(db=db, enrollment_id=enrollment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to remove enrollment — check logs")
