"""Audit trail tests for fee-reminder routing through dispatch.

These tests exercise the dispatch orchestrator directly (rather than via the
full HTTP round-trip) because BackgroundTasks run outside the test request cycle.
"""

import pytest

from models.notification_base import NotificationStatus, NotificationType
from models.parent_base import ParentSchema
from repositories.notification_repository import NotificationRepository
from repositories.parent_repository import ParentRepository
from services import notification_service
from services.notification_service import (
    dispatch_in_background,  # noqa: F401 — import confirms symbol exists
)


@pytest.mark.asyncio
async def test_unverified_fee_reminder_audited_as_skipped(db_session, monkeypatch):
    async def _send(to, template_name, components=None, language="en"):
        return {"messages": [{"id": "wamid.X"}]}

    monkeypatch.setattr(notification_service, "send_template_message", _send)

    parent = ParentSchema(phone_number="9333333333", name="P", user_id=None)
    await ParentRepository().create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session,
        parent=parent,
        student_id=5,
        institute_id=2,
        type=NotificationType.FEE_REMINDER,
        template_name="fee_reminder",
        components=[{"type": "body"}],
        join_url="https://batchbook.in/join/CODE",
    )
    assert log.status == NotificationStatus.SKIPPED_UNVERIFIED

    latest = await NotificationRepository().get_latest_by_student_ids(db_session, [5])
    assert latest[5].status == NotificationStatus.SKIPPED_UNVERIFIED
