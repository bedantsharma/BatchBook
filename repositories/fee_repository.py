from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema


class FeeRepository:
    # ── FeeStructure ──────────────────────────────────────────────────────────

    async def create_or_update_structure(
        self,
        db: AsyncSession,
        batch_id: int,
        monthly_amount: Decimal,
    ) -> FeeStructureSchema:
        result = await db.execute(
            select(FeeStructureSchema).where(FeeStructureSchema.batch_id == batch_id)
        )
        structure = result.scalar_one_or_none()
        if structure:
            structure.monthly_amount = monthly_amount
            await db.commit()
            await db.refresh(structure)
            return structure

        structure = FeeStructureSchema(batch_id=batch_id, monthly_amount=monthly_amount)
        db.add(structure)
        await db.commit()
        await db.refresh(structure)
        return structure

    async def get_structure_by_batch(
        self, db: AsyncSession, batch_id: int
    ) -> FeeStructureSchema | None:
        result = await db.execute(
            select(FeeStructureSchema).where(FeeStructureSchema.batch_id == batch_id)
        )
        return result.scalar_one_or_none()

    # ── FeeRecord ─────────────────────────────────────────────────────────────

    async def bulk_create_records(
        self, db: AsyncSession, records: list[FeeRecordSchema]
    ) -> list[FeeRecordSchema]:
        for record in records:
            db.add(record)
        await db.commit()
        for record in records:
            await db.refresh(record)
        return records

    async def get_records_by_batch_and_month(
        self, db: AsyncSession, batch_id: int, month: date
    ) -> list[FeeRecordSchema]:
        from models.enrollment_base import EnrollmentSchema

        result = await db.execute(
            select(FeeRecordSchema)
            .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
            .where(
                EnrollmentSchema.batch_id == batch_id,
                FeeRecordSchema.month == month,
            )
        )
        return list(result.scalars().all())

    async def get_record_by_id(
        self, db: AsyncSession, record_id: int
    ) -> FeeRecordSchema | None:
        result = await db.execute(
            select(FeeRecordSchema).where(FeeRecordSchema.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_record_by_enrollment_and_month(
        self, db: AsyncSession, enrollment_id: int, month: date
    ) -> FeeRecordSchema | None:
        result = await db.execute(
            select(FeeRecordSchema).where(
                FeeRecordSchema.enrollment_id == enrollment_id,
                FeeRecordSchema.month == month,
            )
        )
        return result.scalar_one_or_none()

    async def update_payment(
        self,
        db: AsyncSession,
        record: FeeRecordSchema,
        amount_paid: Decimal,
        reference: str | None,
    ) -> FeeRecordSchema:
        from datetime import datetime

        record.amount_paid = amount_paid
        record.payment_reference = reference

        if amount_paid >= record.amount_due:
            record.status = FeeStatus.FULLY_PAID
            record.paid_at = datetime.now()
        elif amount_paid > 0:
            record.status = FeeStatus.PARTIALLY_PAID
        else:
            record.status = FeeStatus.NOT_PAID
            record.paid_at = None

        await db.commit()
        await db.refresh(record)
        return record

    async def update_payment_link(
        self,
        db: AsyncSession,
        record: FeeRecordSchema,
        payment_link: str,
    ) -> FeeRecordSchema:
        record.payment_link = payment_link
        await db.commit()
        await db.refresh(record)
        return record
