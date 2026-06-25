from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.razorpay_client import get_razorpay_client
from clients.supabase_client import get_supabase_client
from db.session import get_db
from models.batch_base import BatchSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema
from routes.requests.mark_payment_request import MarkPaymentRequest
from routes.requests.setup_fee_structure_request import SetupFeeStructureRequest
from routes.responses.fee_dashboard_response import FeeDashboardResponse
from routes.responses.fee_record_response import FeeRecordResponse
from routes.responses.fee_structure_response import FeeStructureResponse
from routes.responses.payment_link_response import PaymentLinkResponse
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service

router = APIRouter(prefix="/fee")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


# ─── Auth helpers ─────────────────────────────────────────────────────────────


async def _get_current_owner_user_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    try:
        return await owner_service.get_current_teacher_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def _resolve_institute_id(
    db: AsyncSession,
    owner_user_id: UUID,
    owner_service: OwnerService,
    institute_service: InstituteService,
) -> int:
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


async def _verify_batch_belongs_to_institute(
    db: AsyncSession, batch_id: int, institute_id: int
) -> BatchSchema:
    result = await db.execute(select(BatchSchema).where(BatchSchema.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.institute_id != institute_id:
        raise HTTPException(
            status_code=403,
            detail="Batch does not belong to your institute",
        )
    return batch


def _parse_month(month_str: str) -> date:
    """Parse 'YYYY-MM' into the first day of that month."""
    try:
        parts = month_str.split("-")
        if len(parts) != 2:
            raise ValueError
        return date(int(parts[0]), int(parts[1]), 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="month must be in YYYY-MM format (e.g. 2026-05)",
        )


# ─── POST /fee/structure ──────────────────────────────────────────────────────


@router.post(
    "/structure",
    summary="Set the monthly fee for a batch",
    response_model=FeeStructureResponse,
    status_code=201,
)
async def setup_fee_structure(
    request: SetupFeeStructureRequest,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Create or overwrite the monthly fee amount for a batch.

    If a FeeStructure already exists for this batch, it is updated in place.
    Call ``POST /fee/generate/{batch_id}`` afterwards to create FeeRecord rows
    for the current month.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_batch_belongs_to_institute(db, request.batch_id, institute_id)

    try:
        structure = await fee_service.setup_fee_structure(
            db=db,
            batch_id=request.batch_id,
            monthly_amount=request.monthly_amount,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to set fee structure — check logs")

    return structure


# ─── GET /fee/structure/{batch_id} ───────────────────────────────────────────


@router.get(
    "/structure/{batch_id}",
    summary="Get the fee structure for a batch",
    response_model=FeeStructureResponse,
)
async def get_fee_structure(
    batch_id: int,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_batch_belongs_to_institute(db, batch_id, institute_id)

    structure = await fee_service.get_fee_structure(db=db, batch_id=batch_id)
    if not structure:
        raise HTTPException(
            status_code=404,
            detail="No fee structure found for this batch — set one up first",
        )
    return structure


# ─── POST /fee/generate/{batch_id} ───────────────────────────────────────────


@router.post(
    "/generate/{batch_id}",
    summary="Generate fee records for all active students in a batch for a given month",
    response_model=list[FeeRecordResponse],
    status_code=201,
)
async def generate_monthly_records(
    batch_id: int,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    month: str = Query(..., examples=["2026-05"], description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Create one FeeRecord per active enrolled student for the given month.

    Idempotent: students who already have a record for this month are skipped.
    Returns only the newly created records (empty list if all records already existed).
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_batch_belongs_to_institute(db, batch_id, institute_id)

    month_date = _parse_month(month)

    try:
        records = await fee_service.generate_monthly_records(
            db=db, batch_id=batch_id, month=month_date
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to generate fee records — check logs"
        )

    return records


# ─── PATCH /fee/record/{record_id}/pay ───────────────────────────────────────


@router.patch(
    "/record/{record_id}/pay",
    summary="Record a payment against a fee record",
    response_model=FeeRecordResponse,
)
async def mark_payment(
    record_id: int,
    request: MarkPaymentRequest,
    background_tasks: BackgroundTasks,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Update the amount paid on a fee record.

    Status is derived automatically:
    - amount_paid == 0 → NOT_PAID
    - 0 < amount_paid < amount_due → PARTIALLY_PAID
    - amount_paid >= amount_due → FULLY_PAID (paid_at is set to now)

    When the fee becomes FULLY_PAID, a WhatsApp fee_receipt is sent to the parent
    in the background.
    """
    from models.batch_base import BatchSchema
    from models.fee_record_base import FeeStatus
    from models.parent_base import ParentSchema
    from models.student_base import StudentSchema
    from services.notification_service import send_fee_receipt

    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )

    rec_result = await db.execute(
        select(FeeRecordSchema).where(FeeRecordSchema.id == record_id)
    )
    fee_record = rec_result.scalar_one_or_none()
    if not fee_record:
        raise HTTPException(status_code=404, detail="FeeRecord not found")

    enroll_result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == fee_record.enrollment_id)
    )
    enrollment = enroll_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    await _verify_batch_belongs_to_institute(db, enrollment.batch_id, institute_id)

    try:
        updated = await fee_service.mark_payment(
            db=db,
            record_id=record_id,
            amount_paid=request.amount_paid,
            reference=request.reference,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Failed to record payment — check logs")

    if updated.status == FeeStatus.FULLY_PAID:
        try:
            student_result = await db.execute(
                select(StudentSchema, ParentSchema, BatchSchema)
                .join(ParentSchema, StudentSchema.parent_id == ParentSchema.id, isouter=True)
                .join(BatchSchema, BatchSchema.id == enrollment.batch_id)
                .where(StudentSchema.id == enrollment.student_id)
            )
            row = student_result.first()
            if row:
                student, parent, batch = row
                if parent and parent.phone_number:
                    background_tasks.add_task(
                        send_fee_receipt,
                        parent_phone=parent.phone_number,
                        student_name=student.name or "Student",
                        amount=float(updated.amount_paid),
                        batch_name=batch.name,
                        paid_on=updated.paid_at.strftime("%d %b %Y") if updated.paid_at else "",
                    )
        except Exception as e:
            logger.error(f"Failed to queue fee receipt notification: {e}")

    return updated


# ─── GET /fee/dashboard ───────────────────────────────────────────────────────


@router.get(
    "/dashboard",
    summary="Institute-wide fee summary for a given month",
    response_model=FeeDashboardResponse,
)
async def fee_dashboard(
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    month: str = Query(..., examples=["2026-05"], description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Return totals and per-record breakdown for the whole institute for a month."""
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    month_date = _parse_month(month)

    try:
        dashboard = await fee_service.get_fee_dashboard(
            db=db, institute_id=institute_id, month=month_date
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to build fee dashboard — check logs"
        )

    return dashboard


# ─── GET /fee/batch/{batch_id} ────────────────────────────────────────────────


@router.get(
    "/batch/{batch_id}",
    summary="Fee status list for all students in a batch for a given month",
    response_model=list[FeeRecordResponse],
)
async def get_batch_fees(
    batch_id: int,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    month: str = Query(..., examples=["2026-05"], description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Return all fee records for a batch in a given month."""
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    await _verify_batch_belongs_to_institute(db, batch_id, institute_id)

    month_date = _parse_month(month)

    return await fee_service.get_batch_fee_records(
        db=db, batch_id=batch_id, month=month_date
    )


# ─── GET /fee/record/{record_id}/payment-link ─────────────────────────────────


@router.get(
    "/record/{record_id}/payment-link",
    summary="Generate a Razorpay UPI payment link for a fee record",
    response_model=PaymentLinkResponse,
)
async def get_payment_link(
    record_id: int,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Generate a Razorpay short_url for the pending balance on a fee record.

    The link covers amount_due − amount_paid. Returns 422 if the fee is already
    fully paid. The generated link is persisted on the FeeRecord.payment_link column.
    """
    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )

    rec_result = await db.execute(
        select(FeeRecordSchema).where(FeeRecordSchema.id == record_id)
    )
    fee_record = rec_result.scalar_one_or_none()
    if not fee_record:
        raise HTTPException(status_code=404, detail="FeeRecord not found")

    enroll_result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == fee_record.enrollment_id)
    )
    enrollment = enroll_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    await _verify_batch_belongs_to_institute(db, enrollment.batch_id, institute_id)

    try:
        razorpay_client = get_razorpay_client()
        result = await fee_service.generate_payment_link(
            db=db,
            record_id=record_id,
            razorpay_client=razorpay_client,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to generate payment link — check logs"
        )

    return result


# ─── POST /fee/remind/{record_id} ─────────────────────────────────────────────


@router.post(
    "/remind/{record_id}",
    summary="Send a WhatsApp fee reminder to the parent for a specific fee record",
    status_code=202,
)
async def send_fee_reminder_for_record(
    record_id: int,
    background_tasks: BackgroundTasks,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Queue a WhatsApp fee_reminder message for a single fee record.

    Returns 202 Accepted immediately. The WhatsApp call happens in the background.
    Returns 422 if the fee is already fully paid (no reminder needed).
    """
    from models.batch_base import BatchSchema
    from models.fee_record_base import FeeStatus
    from models.parent_base import ParentSchema
    from models.student_base import StudentSchema
    from services.notification_service import send_fee_reminder

    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )

    rec_result = await db.execute(
        select(FeeRecordSchema).where(FeeRecordSchema.id == record_id)
    )
    fee_record = rec_result.scalar_one_or_none()
    if not fee_record:
        raise HTTPException(status_code=404, detail="FeeRecord not found")

    if fee_record.status == FeeStatus.FULLY_PAID:
        raise HTTPException(status_code=422, detail="Fee is already fully paid")

    enroll_result = await db.execute(
        select(EnrollmentSchema).where(EnrollmentSchema.id == fee_record.enrollment_id)
    )
    enrollment = enroll_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    await _verify_batch_belongs_to_institute(db, enrollment.batch_id, institute_id)

    student_result = await db.execute(
        select(StudentSchema, ParentSchema, BatchSchema)
        .join(ParentSchema, StudentSchema.parent_id == ParentSchema.id, isouter=True)
        .join(BatchSchema, BatchSchema.id == enrollment.batch_id)
        .where(StudentSchema.id == enrollment.student_id)
    )
    row = student_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Student data not found")

    student, parent, batch = row
    if not parent or not parent.phone_number:
        raise HTTPException(status_code=422, detail="No phone number on record for this parent")

    amount_pending = fee_record.amount_due - fee_record.amount_paid
    due_date = f"{enrollment.due_day} {fee_record.month.strftime('%b %Y')}"

    background_tasks.add_task(
        send_fee_reminder,
        parent_phone=parent.phone_number,
        student_name=student.name or "Student",
        amount=float(amount_pending),
        batch_name=batch.name,
        due_date=due_date,
        payment_link=fee_record.payment_link,
    )

    return {"detail": "Reminder queued", "record_id": record_id}


# ─── POST /fee/remind-all ──────────────────────────────────────────────────────


@router.post(
    "/remind-all",
    summary="Send WhatsApp fee reminders to all parents with unpaid fees for a month",
    status_code=202,
)
async def send_fee_reminders_for_all(
    background_tasks: BackgroundTasks,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    month: str = Query(..., examples=["2026-05"], description="Month in YYYY-MM format"),
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Queue WhatsApp fee_reminder messages for every unpaid or partially-paid record
    in the institute for the given month.

    Returns 202 Accepted with the count of reminders queued. Each WhatsApp call
    happens in the background so this endpoint returns instantly regardless of
    how many reminders are sent.
    """
    from models.batch_base import BatchSchema
    from models.fee_record_base import FeeStatus
    from models.parent_base import ParentSchema
    from models.student_base import StudentSchema
    from services.notification_service import send_fee_reminder

    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    month_date = _parse_month(month)

    result = await db.execute(
        select(FeeRecordSchema, EnrollmentSchema, StudentSchema, ParentSchema, BatchSchema)
        .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
        .join(StudentSchema, EnrollmentSchema.student_id == StudentSchema.id)
        .outerjoin(ParentSchema, StudentSchema.parent_id == ParentSchema.id)
        .join(BatchSchema, EnrollmentSchema.batch_id == BatchSchema.id)
        .where(
            BatchSchema.institute_id == institute_id,
            FeeRecordSchema.month == month_date,
            FeeRecordSchema.status != FeeStatus.FULLY_PAID,
        )
    )

    queued = 0
    for fee_record, enrollment, student, parent, batch in result.all():
        if not parent or not parent.phone_number:
            continue
        amount_pending = fee_record.amount_due - fee_record.amount_paid
        due_date = f"{enrollment.due_day} {fee_record.month.strftime('%b %Y')}"
        background_tasks.add_task(
            send_fee_reminder,
            parent_phone=parent.phone_number,
            student_name=student.name or "Student",
            amount=float(amount_pending),
            batch_name=batch.name,
            due_date=due_date,
            payment_link=fee_record.payment_link,
        )
        queued += 1

    return {"detail": f"{queued} reminder(s) queued", "month": month}
