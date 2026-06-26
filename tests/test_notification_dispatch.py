import uuid

import pytest

from models.notification_base import NotificationStatus, NotificationType
from models.parent_base import ParentSchema
from repositories.parent_repository import ParentRepository
from services import notification_service


@pytest.fixture
def fake_send(monkeypatch):
    calls = []

    async def _send(to, template_name, components=None, language="en"):
        calls.append({"to": to, "template_name": template_name, "components": components})
        return {"messages": [{"id": "wamid.TEST"}]}

    monkeypatch.setattr(notification_service, "send_template_message", _send)
    return calls


@pytest.mark.asyncio
async def test_verified_parent_sends_and_logs_sent(db_session, fake_send):
    repo = ParentRepository()
    parent = ParentSchema(phone_number="9876543210", name="A", user_id=uuid.uuid4())
    await repo.create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=1, institute_id=7,
        type=NotificationType.FEE_REMINDER, template_name="fee_reminder",
        components=[{"type": "body"}],
    )
    assert log.status == NotificationStatus.SENT
    assert fake_send[-1]["template_name"] == "fee_reminder"
    assert log.meta_data["whatsapp_response"] == {"messages": [{"id": "wamid.TEST"}]}
    assert log.meta_data["institute_id"] == 7


@pytest.mark.asyncio
async def test_unverified_reminder_sends_invite_and_logs_skipped(db_session, fake_send):
    repo = ParentRepository()
    parent = ParentSchema(phone_number="9000000000", name="B", user_id=None)
    await repo.create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=2, institute_id=7,
        type=NotificationType.FEE_REMINDER, template_name="fee_reminder",
        components=[{"type": "body"}], join_url="https://batchbook.in/join/ABC123",
    )
    assert log.status == NotificationStatus.SKIPPED_UNVERIFIED
    assert log.reason == "parent number not verified"
    assert fake_send[-1]["template_name"] == "enrollment_invite"  # invite sent instead
    assert log.meta_data["whatsapp_response"] == {"messages": [{"id": "wamid.TEST"}]}
    assert log.meta_data["institute_id"] == 7
    assert log.meta_data["message"]  # truthy check


@pytest.mark.asyncio
async def test_send_failure_logs_failed(db_session, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(notification_service, "send_template_message", _boom)
    repo = ParentRepository()
    parent = ParentSchema(phone_number="9222222222", name="C", user_id=uuid.uuid4())
    await repo.create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=3, institute_id=7,
        type=NotificationType.FEE_RECEIPT, template_name="fee_receipt",
        components=[{"type": "body"}],
    )
    assert log.status == NotificationStatus.FAILED
    assert "api down" in (log.reason or "")
