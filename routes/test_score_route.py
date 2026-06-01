from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from models.enrollment_base import EnrollmentSchema
from models.batch_base import BatchSchema
from routes.requests.create_test_score_request import CreateTestScoreRequest
from routes.responses.test_score_response import StudentScoresResponse, TestScoreResponse
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service
from services.test_score_service import ScoreService, get_test_score_service

router = APIRouter(prefix="/scores")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]
ScoreServiceDep = Annotated[ScoreService, Depends(get_test_score_service)]


# ─── Auth helpers ─────────────────────────────────────────────────────────────


async def _get_current_owner_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
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


async def _verify_enrollment_belongs_to_institute(
    db: AsyncSession, enrollment_id: int, institute_id: int
) -> EnrollmentSchema:
    """Verify the enrollment exists and its batch belongs to this institute."""
    result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    batch_result = await db.execute(
        select(BatchSchema).where(BatchSchema.id == enrollment.batch_id)
    )
    batch = batch_result.scalar_one_or_none()
    if not batch or batch.institute_id != institute_id:
        raise HTTPException(
            status_code=403,
            detail="Enrollment does not belong to your institute",
        )
    return enrollment


# ─── POST /scores/ ────────────────────────────────────────────────────────────


@router.post(
    "/",
    summary="Record a test score for a student",
    response_model=TestScoreResponse,
    status_code=201,
)
async def create_test_score(
    request: CreateTestScoreRequest,
    score_service: ScoreServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Enter a test score for a student.

    The ``enrollment_id`` must belong to a batch in the authenticated owner's institute.
    ``obtained_marks`` must not exceed ``max_marks``.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_enrollment_belongs_to_institute(db, request.enrollment_id, institute_id)

    try:
        score = await score_service.add_score(
            db=db,
            enrollment_id=request.enrollment_id,
            test_name=request.test_name,
            subject=request.subject,
            score_date=request.date,
            max_marks=request.max_marks,
            obtained_marks=request.obtained_marks,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to save test score — check logs")

    return score


# ─── GET /scores/student/{enrollment_id} ─────────────────────────────────────


@router.get(
    "/student/{enrollment_id}",
    summary="Get all test scores for a student (with needs_attention flag)",
    response_model=StudentScoresResponse,
)
async def get_student_scores(
    enrollment_id: int,
    score_service: ScoreServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Return all test scores for a student's enrollment.

    Includes a ``needs_attention`` flag that is ``true`` when the average
    percentage of the last 3 scores is below 60 %.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_enrollment_belongs_to_institute(db, enrollment_id, institute_id)

    result = await score_service.get_scores_for_enrollment(db=db, enrollment_id=enrollment_id)
    return result
