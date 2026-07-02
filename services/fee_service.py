import enum
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema
from repositories.fee_repository import FeeRepository


class PaymentMethod(str, enum.Enum):
    """Payment method for a generated Razorpay payment link.

    Only UPI is supported today. More methods (CARD, NETBANKING, ...) can be
    added later without changing generate_payment_link's call signature.
    """

    UPI = "UPI"


def _first_of_last_month() -> date:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    return (first_of_this_month - timedelta(days=1)).replace(day=1)


class FeeService:
    """Business logic for fee structures, fee record generation, and payments.

    Security contract: callers (routes) are responsible for verifying that the
    batch/enrollment belongs to the authenticated owner's institute before
    calling any method here.
    """

    def __init__(self) -> None:
        self.fee_repo = FeeRepository()

    async def setup_fee_structure(
        self,
        db: AsyncSession,
        batch_id: int,
        monthly_amount: Decimal,
    ) -> FeeStructureSchema:
        """Create or overwrite the FeeStructure for a batch.

        Raises:
            ValueError: If monthly_amount is not positive.
        """
        if monthly_amount <= 0:
            raise ValueError("monthly_amount must be greater than 0")
        return await self.fee_repo.create_or_update_structure(db, batch_id, monthly_amount)

    async def get_fee_structure(
        self, db: AsyncSession, batch_id: int
    ) -> FeeStructureSchema | None:
        return await self.fee_repo.get_structure_by_batch(db, batch_id)

    async def generate_monthly_records(
        self,
        db: AsyncSession,
        batch_id: int,
        month: date,
    ) -> list[FeeRecordSchema]:
        """Generate one FeeRecord per active enrollment for a batch + month.

        Idempotent: enrollments that already have a record for this month are
        skipped.  For a student's first month, uses enrollment.first_month_amount
        if set; otherwise falls back to FeeStructure.monthly_amount.

        Raises:
            ValueError: If no FeeStructure exists for the batch.
        """
        from models.enrollment_base import EnrollmentSchema

        structure = await self.fee_repo.get_structure_by_batch(db, batch_id)
        if not structure:
            raise ValueError(
                f"No FeeStructure found for batch {batch_id} — "
                "set up the fee structure first"
            )

        result = await db.execute(
            select(EnrollmentSchema).where(
                EnrollmentSchema.batch_id == batch_id,
                EnrollmentSchema.is_active.is_(True),
            )
        )
        active_enrollments = list(result.scalars().all())

        new_records: list[FeeRecordSchema] = []
        for enrollment in active_enrollments:
            existing = await self.fee_repo.get_record_by_enrollment_and_month(
                db, enrollment.id, month
            )
            if existing:
                continue

            # Use pro-rated first-month amount if set on enrollment
            amount_due = (
                enrollment.first_month_amount
                if enrollment.first_month_amount is not None
                else structure.monthly_amount
            )

            new_records.append(
                FeeRecordSchema(
                    enrollment_id=enrollment.id,
                    month=month,
                    amount_due=amount_due,
                    amount_paid=Decimal("0"),
                    status=FeeStatus.NOT_PAID,
                )
            )

        if new_records:
            await self.fee_repo.bulk_create_records(db, new_records)

        return new_records

    async def mark_payment(
        self,
        db: AsyncSession,
        record_id: int,
        amount_paid: Decimal,
        reference: str | None = None,
    ) -> FeeRecordSchema:
        """Record a payment against a FeeRecord.

        Updates amount_paid, status, and paid_at (when fully paid).

        Raises:
            ValueError: If record not found or amount_paid is negative.
        """
        record = await self.fee_repo.get_record_by_id(db, record_id)
        if not record:
            raise ValueError(f"FeeRecord {record_id} not found")

        if amount_paid < 0:
            raise ValueError("amount_paid cannot be negative")

        return await self.fee_repo.update_payment(db, record, amount_paid, reference)

    async def get_fee_dashboard(
        self,
        db: AsyncSession,
        institute_id: int,
        month: date,
    ) -> dict:
        """Institute-wide fee summary for a given month.

        Returns a dict with:
          - total_due (Decimal)
          - total_collected (Decimal)
          - total_pending (Decimal)
          - collection_rate (float, percent)
          - records (list of dicts with student_name, batch_name, record fields,
                     parent_is_verified, last_notification_status,
                     last_notification_reason)
        """
        from models.batch_base import BatchSchema
        from models.enrollment_base import EnrollmentSchema
        from models.parent_base import ParentSchema
        from models.student_base import StudentSchema
        from repositories.notification_repository import NotificationRepository

        result = await db.execute(
            select(
                FeeRecordSchema,
                EnrollmentSchema,
                StudentSchema,
                BatchSchema,
                ParentSchema,
            )
            .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
            .join(StudentSchema, EnrollmentSchema.student_id == StudentSchema.id)
            .outerjoin(ParentSchema, StudentSchema.parent_id == ParentSchema.id)
            .join(BatchSchema, EnrollmentSchema.batch_id == BatchSchema.id)
            .where(
                BatchSchema.institute_id == institute_id,
                FeeRecordSchema.month == month,
            )
        )
        rows = result.all()

        # Batch-fetch latest notifications for all students in one query (no N+1)
        student_ids = [row[2].id for row in rows]
        latest_notifications = await NotificationRepository().get_latest_by_student_ids(
            db, student_ids
        )

        total_due = Decimal("0")
        total_collected = Decimal("0")
        records_out = []

        for fee_record, _enrollment, student, batch, parent in rows:
            total_due += fee_record.amount_due
            total_collected += fee_record.amount_paid
            note = latest_notifications.get(student.id)
            records_out.append(
                {
                    "id": fee_record.id,
                    "enrollment_id": fee_record.enrollment_id,
                    "student_name": student.name,
                    "batch_name": batch.name,
                    "month": fee_record.month,
                    "amount_due": fee_record.amount_due,
                    "amount_paid": fee_record.amount_paid,
                    "status": fee_record.status,
                    "paid_at": fee_record.paid_at,
                    "payment_reference": fee_record.payment_reference,
                    "payment_link": fee_record.payment_link,
                    "parent_is_verified": parent.user_id is not None if parent else False,
                    "last_notification_status": note.status.value if note else None,
                    "last_notification_reason": note.reason if note else None,
                }
            )

        total_pending = total_due - total_collected
        collection_rate = (
            float(total_collected / total_due * 100) if total_due > 0 else 0.0
        )

        return {
            "total_due": total_due,
            "total_collected": total_collected,
            "total_pending": total_pending,
            "collection_rate": round(collection_rate, 2),
            "records": records_out,
        }

    async def get_batch_fee_records(
        self, db: AsyncSession, batch_id: int, month: date
    ) -> list[dict]:
        """Return fee records for a batch and month, with student_name joined in."""
        from models.enrollment_base import EnrollmentSchema
        from models.student_base import StudentSchema

        result = await db.execute(
            select(FeeRecordSchema, StudentSchema.name)
            .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
            .join(StudentSchema, EnrollmentSchema.student_id == StudentSchema.id)
            .where(
                EnrollmentSchema.batch_id == batch_id,
                FeeRecordSchema.month == month,
            )
        )
        rows = result.all()
        out = []
        for record, student_name in rows:
            out.append({
                "id": record.id,
                "enrollment_id": record.enrollment_id,
                "student_name": student_name,
                "month": record.month,
                "amount_due": record.amount_due,
                "amount_paid": record.amount_paid,
                "status": record.status,
                "paid_at": record.paid_at,
                "payment_reference": record.payment_reference,
                "payment_link": record.payment_link,
                "created_at": record.created_at,
            })
        return out

    async def _create_razorpay_link(self, razorpay_client, data: dict) -> dict:
        """Run the synchronous Razorpay SDK call in a thread pool."""
        import asyncio

        return await asyncio.to_thread(razorpay_client.payment_link.create, data)

    async def generate_payment_link(
        self,
        db: AsyncSession,
        record_id: int,
        razorpay_client,
        payment_method: PaymentMethod | None = PaymentMethod.UPI,
    ) -> dict:
        """Generate a Razorpay payment link for the remaining balance on a FeeRecord.

        payment_method=PaymentMethod.UPI (the default) creates a UPI-only Payment
        Link — opening it on a phone goes straight to a UPI app picker instead of
        Razorpay's standard multi-method checkout page. Pass payment_method=None for
        today's standard link (all payment methods; also the only option that works
        with a test-mode `rzp_test_` key, since UPI Payment Links require live mode).

        Raises:
            ValueError: If the record is not found or is already fully paid.
        """
        record = await self.fee_repo.get_record_by_id(db, record_id)
        if not record:
            raise ValueError(f"FeeRecord {record_id} not found")

        if record.status == FeeStatus.FULLY_PAID:
            raise ValueError("Fee is already fully paid — no payment link needed")

        amount_pending = record.amount_due - record.amount_paid
        amount_paise = int(amount_pending * 100)
        description = f"Fee payment for {record.month.strftime('%B %Y')}"

        settings = get_settings()
        data = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "reminder_enable": True,
            "callback_url": f"{settings.frontend_base_url}/payment-success",
            "callback_method": "get",
        }
        if payment_method == PaymentMethod.UPI:
            data["upi_link"] = "true"

        result = await self._create_razorpay_link(razorpay_client, data)
        payment_link_url = result["short_url"]

        await self.fee_repo.update_payment_link(db, record, payment_link_url)

        return {
            "record_id": record.id,
            "payment_link": payment_link_url,
            "amount_pending": amount_pending,
            "month": record.month,
        }

    async def backfill_missing_payment_links(
        self,
        db: AsyncSession,
        institute_id: int | None = None,
        month: date | None = None,
    ) -> dict:
        """Generate payment links for last month's fee records that don't have one yet.

        Only institutes with a connected Razorpay account are eligible — others are
        counted under skipped_no_razorpay. A failure generating one record's link is
        logged and counted under failed; it does not stop the rest of the batch.
        """
        from clients.razorpay_client import build_institute_razorpay_client

        if month is None:
            month = _first_of_last_month()

        rows = await self.fee_repo.get_records_missing_payment_link_for_month(
            db, month, institute_id
        )

        by_institute = defaultdict(list)
        institutes_by_id = {}
        for record, institute in rows:
            by_institute[institute.id].append(record)
            institutes_by_id[institute.id] = institute

        summary = {
            "month": month,
            "checked": len(rows),
            "generated": 0,
            "skipped_no_razorpay": 0,
            "failed": 0,
            "errors": [],
        }

        for inst_id, records in by_institute.items():
            institute = institutes_by_id[inst_id]
            try:
                razorpay_client = build_institute_razorpay_client(institute)
            except Exception as e:
                logger.error(
                    f"Failed to build Razorpay client for institute {inst_id}: {e}"
                )
                summary["skipped_no_razorpay"] += len(records)
                for record in records:
                    summary["errors"].append({"record_id": record.id, "error": str(e)})
                continue

            if razorpay_client is None:
                summary["skipped_no_razorpay"] += len(records)
                continue

            for record in records:
                try:
                    await self.generate_payment_link(
                        db=db, record_id=record.id, razorpay_client=razorpay_client
                    )
                    summary["generated"] += 1
                except Exception as e:
                    logger.error(f"Failed to backfill payment link for FeeRecord {record.id}: {e}")
                    summary["failed"] += 1
                    summary["errors"].append({"record_id": record.id, "error": str(e)})

        return summary


def get_fee_service() -> FeeService:
    return FeeService()
