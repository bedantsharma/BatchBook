from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.test_score_base import ScoreSchema


class TestScoreRepository:
    async def create(self, db: AsyncSession, score: ScoreSchema) -> ScoreSchema:
        db.add(score)
        await db.commit()
        await db.refresh(score)
        return score

    async def get_by_enrollment_id(
        self, db: AsyncSession, enrollment_id: int
    ) -> list[ScoreSchema]:
        result = await db.execute(
            select(ScoreSchema)
            .where(ScoreSchema.enrollment_id == enrollment_id)
            .order_by(ScoreSchema.date.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, db: AsyncSession, score_id: int) -> ScoreSchema | None:
        result = await db.execute(
            select(ScoreSchema).where(ScoreSchema.id == score_id)
        )
        return result.scalar_one_or_none()
