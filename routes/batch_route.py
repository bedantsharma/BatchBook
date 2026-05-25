from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from routes.requests.assign_teacher_request import AssignTeacherRequest
from routes.requests.create_batch_request import CreateBatchRequest
from routes.requests.update_batch_request import UpdateBatchRequest
from routes.responses.batch_response import BatchResponse, BatchTeacherResponse
from services.batch_service import BatchService, get_batch_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service

router = APIRouter(prefix="/batch")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
BatchServiceDep = Annotated[BatchService, Depends(get_batch_service)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


async def _get_current_owner_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    """Validate the JWT and return the owner's Supabase user UUID."""
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
    """Helper: resolve owner JWT → owner record → institute. Raises 404 if either is missing."""
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


# ─── Create batch ─────────────────────────────────────────────────────────────

@router.post(
    "/",
    summary="Create a new batch for the owner's institute",
    response_model=BatchResponse,
    status_code=201,
)
async def create_batch(
    request: CreateBatchRequest,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        batch = await batch_service.create_batch(
            db=db,
            institute_id=institute_id,
            name=request.name,
            subject=request.subject,
            grade=request.grade,
            start_time=request.start_time,
            end_time=request.end_time,
            days_of_week=request.days_of_week,
            max_capacity=request.max_capacity,
            start_date=request.start_date,
            end_date=request.end_date,
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to create batch")
    return batch


# ─── List batches ──────────────────────────────────────────────────────────────

@router.get(
    "/",
    summary="List all batches for the owner's institute",
    response_model=list[BatchResponse],
)
async def list_batches(
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    return await batch_service.list_batches(db=db, institute_id=institute_id)


# ─── Get one batch ─────────────────────────────────────────────────────────────

@router.get(
    "/{batch_id}",
    summary="Get a single batch by ID",
    response_model=BatchResponse,
)
async def get_batch(
    batch_id: int,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        return await batch_service.get_batch(db=db, batch_id=batch_id, institute_id=institute_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Update batch ──────────────────────────────────────────────────────────────

@router.patch(
    "/{batch_id}",
    summary="Update batch details (name, subject, timing, capacity, end_date, etc.)",
    response_model=BatchResponse,
)
async def update_batch(
    batch_id: int,
    request: UpdateBatchRequest,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        return await batch_service.update_batch(
            db=db,
            batch_id=batch_id,
            institute_id=institute_id,
            updates=request.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Delete batch ──────────────────────────────────────────────────────────────

@router.delete(
    "/{batch_id}",
    summary="Delete a batch (only if it has no active enrollments)",
    status_code=204,
)
async def delete_batch(
    batch_id: int,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        await batch_service.delete_batch(
            db=db, batch_id=batch_id, institute_id=institute_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Assign teacher to batch ───────────────────────────────────────────────────

@router.post(
    "/{batch_id}/assign-teacher",
    summary="Assign a teacher to this batch",
    response_model=BatchTeacherResponse,
    status_code=201,
)
async def assign_teacher(
    batch_id: int,
    request: AssignTeacherRequest,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        return await batch_service.assign_teacher(
            db=db,
            batch_id=batch_id,
            teacher_id=request.teacher_id,
            institute_id=institute_id,
        )
    except ValueError as e:
        status_code = 409 if "already assigned" in str(e) else 404
        raise HTTPException(status_code=status_code, detail=str(e))


# ─── Remove teacher from batch ─────────────────────────────────────────────────

@router.delete(
    "/{batch_id}/teacher/{teacher_id}",
    summary="Remove a teacher from this batch",
    status_code=204,
)
async def remove_teacher(
    batch_id: int,
    teacher_id: int,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        await batch_service.remove_teacher(
            db=db,
            batch_id=batch_id,
            teacher_id=teacher_id,
            institute_id=institute_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Archive batch ─────────────────────────────────────────────────────────────

@router.post(
    "/{batch_id}/archive",
    summary="Attempt to archive a batch (fails if there are unsettled fee records)",
    response_model=BatchResponse,
)
async def archive_batch(
    batch_id: int,
    batch_service: BatchServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_id),
):
    institute_id = await _get_institute_id(db, owner_user_id, owner_service, institute_service)
    try:
        return await batch_service.try_archive(
            db=db, batch_id=batch_id, institute_id=institute_id
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
