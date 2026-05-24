from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from clients.supabase_client import get_supabase_client
from db.session import get_db
from routes.requests.invite_teacher_request import InviteTeacherRequest
from routes.requests.refresh_token_request import RefreshTokenRequest
from routes.requests.teacher_verify_otp_request import TeacherVerifyOtpRequest
from routes.responses.teacher_profile_response import TeacherProfileResponse
from routes.responses.verify_teacher_response import VerifyTeacherResponse
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service
from services.teacher_service import TeacherService, get_teacher_service

router = APIRouter(prefix="/teacher")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
TeacherServiceDep = Annotated[TeacherService, Depends(get_teacher_service)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


async def _get_current_teacher_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    teacher_service: TeacherServiceDep,
) -> UUID:
    try:
        return await teacher_service.get_current_teacher_user_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _get_current_owner_teacher_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    """Returns the Supabase user UUID for an authenticated owner (used on owner-only endpoints)."""
    try:
        return await owner_service.get_current_teacher_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post(
    "/invite",
    summary="Owner invites a teacher — creates a Teacher record and sends OTP to their phone",
    response_model=TeacherProfileResponse,
    status_code=201,
)
async def invite_teacher(
    request: InviteTeacherRequest,
    teacher_service: TeacherServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
    owner_teacher_id: UUID = Depends(_get_current_owner_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=owner_teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")

    institute = await institute_service.get_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(
            status_code=404, detail="Institute not set up yet — please create an institute first"
        )

    try:
        teacher = await teacher_service.invite_teacher(
            supabase=supabase,
            db=db,
            institute_id=institute.id,
            name=request.name,
            phone=request.phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to invite teacher — check logs")

    return teacher


@router.post(
    "/verify_otp",
    summary="Teacher activates their account by verifying the OTP received on their phone",
    response_model=VerifyTeacherResponse,
)
async def verify_otp(
    request: TeacherVerifyOtpRequest,
    teacher_service: TeacherServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        access_token, refresh_token, aud, user_id = await teacher_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=request.phone,
            token=request.token,
        )
    except (ValueError, AuthApiError) as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Could not communicate with Supabase — check logs"
        )

    return VerifyTeacherResponse(
        auth_token=access_token,
        refresh_token=refresh_token,
        aud=aud,
        user_id=str(user_id),
    )


@router.get(
    "/me",
    summary="Get the authenticated teacher's profile",
    response_model=TeacherProfileResponse,
)
async def get_teacher_me(
    teacher_service: TeacherServiceDep,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(_get_current_teacher_user_id),
):
    teacher = await teacher_service.get_teacher_by_user_id(db=db, user_id=user_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher record not found")
    return teacher


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new access token + refresh token pair",
    response_model=VerifyTeacherResponse,
)
async def refresh_token(request: RefreshTokenRequest, supabase: SupabaseClient):
    try:
        data = await supabase.auth.refresh_session(request.refresh_token)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if not data.user or not data.session:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return VerifyTeacherResponse(
        auth_token=data.session.access_token,
        refresh_token=data.session.refresh_token,
        aud=data.user.aud,
        user_id=str(data.user.id),
    )


@router.get(
    "/",
    summary="Owner lists all teachers in their institute",
    response_model=list[TeacherProfileResponse],
)
async def list_teachers(
    teacher_service: TeacherServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_teacher_id: UUID = Depends(_get_current_owner_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=owner_teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")

    institute = await institute_service.get_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(status_code=404, detail="Institute not set up yet")

    return await teacher_service.get_teachers_by_institute(db=db, institute_id=institute.id)


@router.delete(
    "/{teacher_id}",
    summary="Owner removes a teacher from their institute",
    status_code=204,
)
async def remove_teacher(
    teacher_id: int,
    teacher_service: TeacherServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_teacher_id: UUID = Depends(_get_current_owner_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=owner_teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")

    institute = await institute_service.get_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(status_code=404, detail="Institute not set up yet")

    try:
        await teacher_service.remove_teacher(
            db=db, institute_id=institute.id, teacher_id=teacher_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
