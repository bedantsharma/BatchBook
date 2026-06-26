"""Audit trail tests for fee-reminder routing through dispatch.

These tests exercise the dispatch orchestrator directly (rather than via the
full HTTP round-trip) because BackgroundTasks run outside the test request cycle.
"""

import pytest

from models.notification_base import NotificationSchema, NotificationStatus, NotificationType
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


@pytest.mark.asyncio
async def test_enrollment_invite_always_sends_and_audits_as_sent(db_session, monkeypatch):
    """Fix 2: ENROLLMENT_INVITE is not a reminder type — dispatch must always attempt the
    send (regardless of verification) and write a SENT audit row.

    This verifies the dispatch-level contract that the enrollment invite route now relies on.
    """
    async def _send(to, template_name, components=None, language="en"):
        return {"messages": [{"id": "wamid.INVITE_AUDIT"}]}

    monkeypatch.setattr(notification_service, "send_template_message", _send)

    # Deliberately unverified parent — dispatch must still send for ENROLLMENT_INVITE
    parent = ParentSchema(phone_number="9555444333", name="E", user_id=None)
    await ParentRepository().create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session,
        parent=parent,
        student_id=20,
        institute_id=5,
        type=NotificationType.ENROLLMENT_INVITE,
        template_name="enrollment_invite",
        components=[
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Arjun"},
                    {"type": "text", "text": "Smart Classes"},
                    {"type": "text", "text": "https://batchbook.in/join/DEF"},
                ],
            }
        ],
        join_url="https://batchbook.in/join/DEF",
    )

    assert log.status == NotificationStatus.SENT
    assert log.type == NotificationType.ENROLLMENT_INVITE
    assert log.meta_data["whatsapp_response"] == {"messages": [{"id": "wamid.INVITE_AUDIT"}]}

    # Confirm the row is persisted and queryable
    from sqlalchemy import select

    result = await db_session.execute(
        select(NotificationSchema).where(NotificationSchema.student_id == 20)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.type == NotificationType.ENROLLMENT_INVITE
    assert row.status == NotificationStatus.SENT
