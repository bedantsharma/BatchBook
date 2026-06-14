from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from clients.supabase_client import get_supabase_client
from db.session import get_db
from models.attendance_base import AttendanceSchema, AttendanceStatus
from models.batch_base import BatchSchema
from models.class_session_base import ClassSessionSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema
from routes.requests.create_institute_request import CreateInstituteRequest
from routes.requests.otp_generate_request import OtpGenerateRequest
from routes.requests.owner_verify_otp_request import OwnerVerifyOtpRequest
from routes.requests.refresh_token_request import RefreshTokenRequest
from routes.requests.update_owner_request import UpdateOwnerRequest
from routes.responses.institute_qr_response import InstituteQRResponse
from routes.responses.institute_response import InstituteResponse
from routes.responses.owner_profile_response import OwnerProfileResponse
from routes.responses.owner_stats_response import OwnerStatsResponse
from routes.responses.verify_owner_response import VerifyOwnerResponse
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service

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
        raise HTTPException(status_code=500, detail="Internal server error — check logs")
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
    summary="Create the owner's institute (allowed only once per owner)",
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

    existing = await institute_service.get_institute_by_owner_id(db=db, owner_id=owner.id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Institute already exists for this owner. Use GET /owner/institute to retrieve it.",
        )

    try:
        institute = await institute_service.create_institute(
            db=db,
            owner_id=owner.id,
            name=request.name,
            city=request.city,
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Could not create institute")

    return institute


@router.get(
    "/institute",
    summary="Get the authenticated owner's institute details",
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

    institute = await institute_service.get_institute_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(
            status_code=404,
            detail="No institute found. Use POST /owner/institute to create one.",
        )

    return institute


@router.get(
    "/stats",
    summary="Headline stats for the owner dashboard — enrolled students, fees collected this month, avg attendance this month",
    response_model=OwnerStatsResponse,
)
async def get_owner_stats(
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    institute_service: InstituteServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    institute = await institute_service.get_institute_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(status_code=404, detail="No institute found for this owner")

    institute_id = institute.id
    today = date.today()
    month_start = date(today.year, today.month, 1)

    enrolled_result = await db.execute(
        select(func.count(EnrollmentSchema.id))
        .join(BatchSchema, EnrollmentSchema.batch_id == BatchSchema.id)
        .where(
            BatchSchema.institute_id == institute_id,
            EnrollmentSchema.is_active.is_(True),
        )
    )
    enrolled_students: int = enrolled_result.scalar_one() or 0

    fees_result = await db.execute(
        select(func.coalesce(func.sum(FeeRecordSchema.amount_paid), 0))
        .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
        .join(BatchSchema, EnrollmentSchema.batch_id == BatchSchema.id)
        .where(
            BatchSchema.institute_id == institute_id,
            FeeRecordSchema.month == month_start,
        )
    )
    fees_collected_this_month: Decimal = Decimal(str(fees_result.scalar_one() or 0))

    sessions_result = await db.execute(
        select(ClassSessionSchema.id)
        .join(BatchSchema, ClassSessionSchema.batch_id == BatchSchema.id)
        .where(
            BatchSchema.institute_id == institute_id,
            ClassSessionSchema.date >= month_start,
            ClassSessionSchema.date <= today,
        )
    )
    session_ids = [row[0] for row in sessions_result.all()]

    avg_attendance: float = 0.0
    if session_ids:
        total_result = await db.execute(
            select(func.count(AttendanceSchema.id)).where(
                AttendanceSchema.session_id.in_(session_ids)
            )
        )
        present_result = await db.execute(
            select(func.count(AttendanceSchema.id)).where(
                AttendanceSchema.session_id.in_(session_ids),
                AttendanceSchema.status == AttendanceStatus.PRESENT,
            )
        )
        total = total_result.scalar_one() or 0
        present = present_result.scalar_one() or 0
        avg_attendance = round((present / total * 100), 1) if total > 0 else 0.0

    return OwnerStatsResponse(
        enrolled_students=enrolled_students,
        fees_collected_this_month=fees_collected_this_month,
        avg_attendance_this_month=avg_attendance,
    )


# ─── GET /owner/institute/qr ──────────────────────────────────────────────────


@router.get(
    "/institute/qr",
    summary="Get the institute's join code and QR URL for sharing with parents",
    response_model=InstituteQRResponse,
)
async def get_institute_qr(
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=owner_user_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    institute = await institute_service.get_institute_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(status_code=404, detail="Institute not set up yet")

    base_url = "https://batchbookui.vercel.app"  # TODO: replace with real domain after Task C.1
    join_url = f"{base_url}/join/{institute.join_code}"

    return InstituteQRResponse(
        join_code=institute.join_code,
        join_url=join_url,
        institute_name=institute.name,
        owner_phone=owner.phone_number,
    )
