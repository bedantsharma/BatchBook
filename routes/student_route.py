from typing import Annotated
from fastapi import APIRouter, Depends
from loguru import logger
from fastapi import HTTPException
from supabase import AsyncClient
from.requests.otp_generate_request import OtpGenerateRequest
from .requests.otp_verify_request import OtpVerifyRequest
from services.student_service import StudentService
from DTO.student_model import Student
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db
from clients.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/student",
)

SupabaseClient = Annotated[AsyncClient,Depends(get_supabase_client)]

@router.post("/")
async def create_user(user: Student, db: AsyncSession= Depends(get_db)):
    logger.info(f"create user called with {user}")
    student_service = StudentService()
    return await student_service.create_student(data=user,db=db)


@router.post("/generate_otp")
async def send_otp(
            request: OtpGenerateRequest,
            supabase: SupabaseClient,
            summary= "generate otp for the given phone number"
    ):
    try:
        data = await supabase.auth.sign_in_with_otp({
            "phone": f"+91{request.phone}",
        })
        return data

    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500,detail="could not communicate with supabase server properly check the logs")

@router.post("/verif_otp")
async def verify_otp(
        verify_request: OtpVerifyRequest,
        supabase: SupabaseClient,
        db: AsyncSession= Depends(get_db),
        summary = "verify otp code"
    ):
    try:
        data = await supabase.auth.verify_otp({
            "phone": f"+91{verify_request.phone}",
            "token": verify_request.token,
            "type":"sms"
        })
        create_user(data,db=db)
        return data
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="could not communicate with supabase server properly check the logs")