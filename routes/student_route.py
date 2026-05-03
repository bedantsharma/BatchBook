from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from supabase import AsyncClient
from .requests.otp_generate_request import OtpGenerateRequest
from .requests.otp_verify_request import OtpVerifyRequest
from .requests.update_student_request import UpdateStudentRequest
from .responses.verify_user_response import VerifyUserResponse
from services.student_service import StudentService
from DTO.student_model import Student
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from clients.supabase_client import get_supabase_client


router = APIRouter(prefix="/student")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]


async def _get_current_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
) -> UUID:
    """Extract and validate the Supabase JWT from the Authorization header."""
    token = authorization.removeprefix("Bearer ").strip()
    try:
        response = await supabase.auth.get_user(token)
        return UUID(str(response.user.id))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post(
    "/",
    summary="Create a new student record directly (internal / admin use)",
)
async def create_user(user: Student, db: AsyncSession = Depends(get_db)):
    logger.info(f"create user called with {user}")
    student_service = StudentService()
    return await student_service.create_student(data=user, db=db)


@router.post(
    "/generate_otp",
    summary="Send an OTP to the given Indian mobile number via Supabase",
)
async def send_otp(request: OtpGenerateRequest, supabase: SupabaseClient):
    try:
        data = await supabase.auth.sign_in_with_otp({
            "phone": f"+91{request.phone}",
        })
        return data
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )


@router.post(
    "/verify_otp",
    summary="Verify the OTP and upsert the student record; returns a JWT for subsequent requests",
    response_model=VerifyUserResponse,
)
async def verify_otp(
    verify_request: OtpVerifyRequest,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await supabase.auth.verify_otp({
            "phone": f"+91{verify_request.phone}",
            "token": verify_request.token,
            "type": "sms",
        })
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )

    if not data.user or not data.session:
        raise HTTPException(status_code=401, detail="OTP verification failed")

    user_id = UUID(str(data.user.id))

    try:
        student_service = StudentService()
        await student_service.get_or_create_after_otp(
            db=db,
            user_id=user_id,
            phone=verify_request.phone,
            name=verify_request.name,
            email=verify_request.email,
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to upsert student record — check logs")

    return VerifyUserResponse(
        auth_token=data.session.access_token,
        aud=data.user.aud,
        user_id=str(user_id),
    )


@router.patch(
    "/update",
    summary="Update the authenticated student's profile fields (name, email, fees_status)",
)
async def update_student(
    update_request: UpdateStudentRequest,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    student_service = StudentService()
    updates = update_request.model_dump(exclude_none=True)
    updated = await student_service.update_student(db=db, user_id=user_id, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Student record not found")
    return updated
