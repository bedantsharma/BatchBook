import pytest

from models.notification_base import NotificationSchema, NotificationStatus, NotificationType
from repositories.notification_repository import NotificationRepository


@pytest.mark.asyncio
async def test_create_and_latest_by_student(db_session):
    repo = NotificationRepository()
    older = NotificationSchema(
        student_id=1, type=NotificationType.FEE_REMINDER,
        status=NotificationStatus.SENT, meta_data={"message": "a"},
    )
    newer = NotificationSchema(
        student_id=1, type=NotificationType.FEE_REMINDER,
        status=NotificationStatus.SKIPPED_UNVERIFIED, reason="parent number not verified",
        meta_data={"message": "b"},
    )
    await repo.create(db_session, older)
    created = await repo.create(db_session, newer)
    assert created.id is not None

    latest = await repo.get_latest_by_student_ids(db_session, [1, 999])
    assert latest[1].status == NotificationStatus.SKIPPED_UNVERIFIED
    assert 999 not in latest
