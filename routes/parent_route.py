from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from clients.supabase_client import get_supabase_client
from db.session import get_db
from services.parent_service import ParentService, get_parent_service
from routes.requests.otp_generate_request import OtpGenerateRequest
from routes.requests.parent_verify_otp_request import ParentVerifyOtpRequest
from routes.requests.refresh_token_request import RefreshTokenRequest
from routes.responses.parent_profile_response import ParentProfileResponse, StudentSummary
from routes.responses.verify_parent_response import VerifyParentResponse, StudentSummaryInToken

router = APIRouter(prefix="/parent")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
ParentServiceDep = Annotated[ParentService, Depends(get_parent_service)]


async def _get_current_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    parent_service: ParentServiceDep,
) -> UUID:
    try:
        return await parent_service.get_current_user_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post(
    "/generate_otp",
    summary="Send an OTP to the given Indian mobile number (parent/student-app login)",
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
    summary="Verify OTP and upsert parent record; returns JWT + list of children",
    response_model=VerifyParentResponse,
)
async def verify_otp(
    verify_request: ParentVerifyOtpRequest,
    parent_service: ParentServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        access_token, refresh_token, aud, user_id, children = await parent_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=verify_request.phone,
            token=verify_request.token,
            name=verify_request.name,
        )
    except (ValueError, AuthApiError) as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="OTP verification failed due to a server error — check backend logs.",
        )
    children_summary = [
        StudentSummaryInToken(id=c.id, name=c.name, fees_status=c.fees_status.value)
        for c in children
    ]
    return VerifyParentResponse(
        auth_token=access_token,
        refresh_token=refresh_token,
        aud=aud,
        user_id=str(user_id),
        children=children_summary,
    )


@router.get(
    "/me",
    summary="Fetch the authenticated parent's profile and their children",
    response_model=ParentProfileResponse,
)
async def get_parent(
    parent_service: ParentServiceDep,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    parent = await parent_service.get_parent_by_user_id(db=db, user_id=user_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent record not found")
    children = await parent_service.get_children(db=db, user_id=user_id)
    children_summary = [
        StudentSummary(
            id=c.id,
            name=c.name,
            email=c.email,
            fees_status=c.fees_status.value,
            institute_id=c.institute_id,
        )
        for c in children
    ]
    return ParentProfileResponse(
        id=parent.id,
        name=parent.name,
        phone_number=parent.phone_number,
        created_at=parent.created_at,
        children=children_summary,
    )


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new access token + refresh token pair",
    response_model=VerifyParentResponse,
)
async def refresh_token(request: RefreshTokenRequest, supabase: SupabaseClient):
    try:
        data = await supabase.auth.refresh_session(request.refresh_token)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if not data.user or not data.session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return VerifyParentResponse(
        auth_token=data.session.access_token,
        refresh_token=data.session.refresh_token,
        aud=data.user.aud,
        user_id=str(data.user.id),
        children=[],
    )
