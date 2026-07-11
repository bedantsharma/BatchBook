from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from clients.supabase_client import get_supabase_client
from db.session import get_db
from DTO.student_model import Student
from rate_limiter import limiter
from services.parent_service import ParentService, get_parent_service
from services.student_service import StudentService, get_student_service

from .requests.otp_generate_request import OtpGenerateRequest
from .requests.otp_verify_request import OtpVerifyRequest
from .requests.refresh_token_request import RefreshTokenRequest
from .responses.verify_parent_response import StudentSummaryInToken, VerifyParentResponse

router = APIRouter(prefix="/student")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
StudentServiceDep = Annotated[StudentService, Depends(get_student_service)]
ParentServiceDep = Annotated[ParentService, Depends(get_parent_service)]


@router.post(
    "/",
    summary="Create a new student record directly (internal / admin use)",
)
async def create_student(
    user: Student,
    student_service: StudentServiceDep,
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"create student called with {user}")
    return await student_service.create_student(
        db=db,
        name=user.name,
        parent_id=user.parent_id,
        institute_id=user.institute_id,
        email=user.email,
    )


@router.post(
    "/generate_otp",
    summary="Send an OTP to the given Indian mobile number via Supabase (student-app / parent login)",
    description=(
        "Initiates phone OTP for the student-app login flow. "
        "Authentication is parent-based: verify_otp returns a Parent JWT plus the list of children. "
        "Use POST /parent/generate_otp for the canonical endpoint."
    ),
)
@limiter.limit("5/minute")
async def send_otp(request: Request, body: OtpGenerateRequest, supabase: SupabaseClient):
    try:
        return await supabase.auth.sign_in_with_otp({"phone": f"+91{body.phone}"})
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )


@router.post(
    "/verify_otp",
    summary="Verify OTP; upserts Parent record and returns JWT + list of children",
    description=(
        "Verifies the SMS OTP. On success, creates or retrieves the Parent record "
        "and returns an access token plus the list of child Student records linked to this parent. "
        "Use POST /parent/verify_otp for the canonical endpoint."
    ),
    response_model=VerifyParentResponse,
)
@limiter.limit("10/minute")
async def verify_otp(
    request: Request,
    verify_request: OtpVerifyRequest,
    parent_service: ParentServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        (
            access_token,
            refresh_token,
            aud,
            user_id,
            parent_name,
            children,
        ) = await parent_service.verify_otp(
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
        StudentSummaryInToken(id=c.id, name=c.name, email=c.email, fees_status=c.fees_status.value)
        for c in children
    ]
    return VerifyParentResponse(
        auth_token=access_token,
        refresh_token=refresh_token,
        aud=aud,
        user_id=str(user_id),
        parent_name=parent_name,
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
