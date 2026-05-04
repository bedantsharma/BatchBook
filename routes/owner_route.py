from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from services.owner_service import OwnerService, get_owner_service
from routes.requests.otp_generate_request import OtpGenerateRequest
from routes.requests.owner_verify_otp_request import OwnerVerifyOtpRequest
from routes.requests.update_owner_request import UpdateOwnerRequest
from routes.responses.owner_profile_response import OwnerProfileResponse
from routes.responses.verify_owner_response import VerifyOwnerResponse

router = APIRouter(prefix="/owner")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]


async def _get_current_teacher_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    try:
        return await owner_service.get_current_teacher_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post(
    "/generate_otp",
    summary="Send an OTP to the given Indian mobile number (owner login)",
)
async def send_otp(request: OtpGenerateRequest, supabase: SupabaseClient):
    try:
        return await supabase.auth.sign_in_with_otp({"phone": f"+91{request.phone}"})
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )


@router.post(
    "/verify_otp",
    summary="Verify OTP and upsert owner record; returns a JWT",
    response_model=VerifyOwnerResponse,
)
async def verify_otp(
    verify_request: OwnerVerifyOtpRequest,
    owner_service: OwnerServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        access_token, aud, teacher_id = await owner_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=verify_request.phone,
            token=verify_request.token,
            name=verify_request.name,
            email=verify_request.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )
    return VerifyOwnerResponse(auth_token=access_token, aud=aud, teacher_id=str(teacher_id))


@router.get(
    "/me",
    summary="Fetch the authenticated owner's profile",
    response_model=OwnerProfileResponse,
)
async def get_owner(
    owner_service: OwnerServiceDep,
    db: AsyncSession = Depends(get_db),
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    return owner


@router.patch(
    "/update",
    summary="Update the authenticated owner's profile (name, email, institute_name, city)",
    response_model=OwnerProfileResponse,
)
async def update_owner(
    update_request: UpdateOwnerRequest,
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    updates = update_request.model_dump(exclude_none=True)
    updated = await owner_service.update_owner(db=db, teacher_id=teacher_id, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Owner record not found")
    return updated
