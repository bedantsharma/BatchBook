from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from models.test_score_base import ScoreSchema
from repositories.test_score_repository import TestScoreRepository

# A student needs attention if the average of their last 3 scores is below this fraction.
NEEDS_ATTENTION_THRESHOLD = 0.60


class ScoreService:
    def __init__(self) -> None:
        self.repo = TestScoreRepository()

    async def add_score(
        self,
        db: AsyncSession,
        enrollment_id: int,
        test_name: str,
        subject: str,
        score_date: date,
        max_marks: int,
        obtained_marks: int,
    ) -> ScoreSchema:
        """Record a test score for a student's enrollment.

        Raises:
            ValueError: If obtained_marks > max_marks or either is non-positive.
        """
        if max_marks <= 0:
            raise ValueError("max_marks must be positive")
        if obtained_marks < 0:
            raise ValueError("obtained_marks cannot be negative")
        if obtained_marks > max_marks:
            raise ValueError("obtained_marks cannot exceed max_marks")

        score = ScoreSchema(
            enrollment_id=enrollment_id,
            test_name=test_name,
            subject=subject,
            date=score_date,
            max_marks=max_marks,
            obtained_marks=obtained_marks,
        )
        return await self.repo.create(db, score)

    async def get_scores_for_enrollment(
        self, db: AsyncSession, enrollment_id: int
    ) -> dict:
        """Return all scores for an enrollment with a needs_attention flag.

        needs_attention is True when the average percentage of the last 3 scores
        is below 60 %.  Returns False when fewer than 3 scores exist (not enough data).
        """
        scores = await self.repo.get_by_enrollment_id(db, enrollment_id)

        needs_attention = False
        if len(scores) >= 3:
            last_three = scores[:3]
            avg_pct = sum(s.obtained_marks / s.max_marks for s in last_three) / 3
            needs_attention = avg_pct < NEEDS_ATTENTION_THRESHOLD

        return {
            "enrollment_id": enrollment_id,
            "scores": scores,
            "needs_attention": needs_attention,
        }


def get_test_score_service() -> ScoreService:
    return ScoreService()
