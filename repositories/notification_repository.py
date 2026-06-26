from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification_base import NotificationSchema


class NotificationRepository:
    async def create(
        self, db: AsyncSession, notification: NotificationSchema
    ) -> NotificationSchema:
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        return notification

    async def get_latest_by_student_ids(
        self, db: AsyncSession, student_ids: list[int]
    ) -> dict[int, NotificationSchema]:
        if not student_ids:
            return {}
        result = await db.execute(
            select(NotificationSchema)
            .where(NotificationSchema.student_id.in_(student_ids))
            .order_by(NotificationSchema.created_at.desc(), NotificationSchema.id.desc())
        )
        latest: dict[int, NotificationSchema] = {}
        for row in result.scalars().all():
            if row.student_id not in latest:
                latest[row.student_id] = row
        return latest
