from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from clients.supabase_client import get_supabase_client
from db.session import get_db
from services.owner_service import OwnerService, get_owner_service
from services.institute_service import InstituteService, get_institute_service
from routes.requests.otp_generate_request import OtpGenerateRequest
from routes.requests.owner_verify_otp_request import OwnerVerifyOtpRequest
from routes.requests.refresh_token_request import RefreshTokenRequest
from routes.requests.update_owner_request import UpdateOwnerRequest
from routes.requests.create_institute_request import CreateInstituteRequest
from routes.responses.owner_profile_response import OwnerProfileResponse
from routes.responses.verify_owner_response import VerifyOwnerResponse
from routes.responses.institute_response import InstituteResponse

router = APIRouter(prefix="/owner")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


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
    summary="Send an OTP to  ithe given Indian mobile number (owner login)",
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
        access_token, refresh_token, aud, teacher_id = await owner_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=verify_request.phone,
            token=verify_request.token,
            name=verify_request.name,
            email=verify_request.email,
        )
    except (ValueError, AuthApiError) as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )
    return VerifyOwnerResponse(auth_token=access_token, refresh_token=refresh_token, aud=aud, teacher_id=str(teacher_id))


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


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new access token + refresh token pair",
    response_model=VerifyOwnerResponse,
)
async def refresh_token(request: RefreshTokenRequest, supabase: SupabaseClient):
    try:
        data = await supabase.auth.refresh_session(request.refresh_token)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if not data.user or not data.session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return VerifyOwnerResponse(
        auth_token=data.session.access_token,
        refresh_token=data.session.refresh_token,
        aud=data.user.aud,
        teacher_id=str(data.user.id),
    )


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


@router.post(
    "/institute",
    summary="Set up the owner's institute (name and city). Only allowed once per owner.",
    response_model=InstituteResponse,
    status_code=201,
)
async def create_institute(
    request: CreateInstituteRequest,
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    institute_service: InstituteServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    try:
        institute = await institute_service.create_institute(
            db=db, owner_id=owner.id, name=request.name, city=request.city
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return institute


@router.get(
    "/institute",
    summary="Get the authenticated owner's institute details.",
    response_model=InstituteResponse,
)
async def get_institute(
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    institute_service: InstituteServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    institute = await institute_service.get_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(status_code=404, detail="Institute not set up yet")
    return institute
