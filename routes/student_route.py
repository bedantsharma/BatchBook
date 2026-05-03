from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from DTO.student_model import Student
from services.student_service import StudentService

from .requests.otp_generate_request import OtpGenerateRequest
from .requests.otp_verify_request import OtpVerifyRequest
from .requests.update_student_request import UpdateStudentRequest
from .responses.verify_user_response import VerifyUserResponse

router = APIRouter(prefix="/student")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]


def get_student_service() -> StudentService:
    return StudentService()


StudentServiceDep = Annotated[StudentService, Depends(get_student_service)]


async def _get_current_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    student_service: StudentServiceDep,
) -> UUID:
    try:
        return await student_service.get_current_user_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post(
    "/",
    summary="Create a new student record directly (internal / admin use)",
)
async def create_user(
    user: Student,
    db: AsyncSession = Depends(get_db),
    student_service: StudentServiceDep = None,
):
    logger.info(f"create user called with {user}")
    return await student_service.create_student(data=user, db=db)


@router.post(
    "/generate_otp",
    summary="Send an OTP to the given Indian mobile number via Supabase",
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
    summary="Verify the OTP and upsert the student record; returns a JWT for subsequent requests",
    response_model=VerifyUserResponse,
)
async def verify_otp(
    verify_request: OtpVerifyRequest,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
    student_service: StudentServiceDep = None,
):
    try:
        access_token, aud, user_id = await student_service.verify_otp(
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
    return VerifyUserResponse(auth_token=access_token, aud=aud, user_id=str(user_id))


@router.patch(
    "/update",
    summary="Update the authenticated student's profile fields (name, email, fees_status)",
)
async def update_student(
    update_request: UpdateStudentRequest,
    db: AsyncSession = Depends(get_db),
    student_service: StudentServiceDep = None,
    user_id: UUID = Depends(_get_current_user_id),
):
    updates = update_request.model_dump(exclude_none=True)
    updated = await student_service.update_student(db=db, user_id=user_id, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Student record not found")
    return updated
