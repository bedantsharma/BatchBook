from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.test_score_base import TestScoreSchema


class TestScoreRepository:
    async def create(self, db: AsyncSession, score: TestScoreSchema) -> TestScoreSchema:
        db.add(score)
        await db.commit()
        await db.refresh(score)
        return score

    async def get_by_enrollment_id(
        self, db: AsyncSession, enrollment_id: int
    ) -> list[TestScoreSchema]:
        result = await db.execute(
            select(TestScoreSchema)
            .where(TestScoreSchema.enrollment_id == enrollment_id)
            .order_by(TestScoreSchema.date.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, db: AsyncSession, score_id: int) -> TestScoreSchema | None:
        result = await db.execute(
            select(TestScoreSchema).where(TestScoreSchema.id == score_id)
        )
        return result.scalar_one_or_none()
