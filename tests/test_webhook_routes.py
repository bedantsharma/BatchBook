"""
Integration tests for routes/webhook_route.py — POST /webhooks/razorpay/{institute_id}.

Seeds real Institute/Enrollment/FeeRecord rows in the test DB and signs request
bodies with real HMAC-SHA256, exercising the same signature verification path
Razorpay uses in production. notification_service.send_fee_receipt is patched
to avoid a real network call.
"""

import hashlib
import hmac
import json
import secrets
import string
from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from models.batch_base import BatchSchema, BatchStatus
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.institute_base import InstituteSchema, RazorpayStatus
from models.owner_base import OwnerSchema
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from services.crypto_service import encrypt_secret

WEBHOOK_SECRET = "whsec_test_secret_value"


def _join_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def _seed_institute(db, webhook_secret: str | None = WEBHOOK_SECRET) -> InstituteSchema:
    owner = OwnerSchema(
        name="Owner", phone_number=f"9{uuid4().int % 10**9:09d}", teacher_id=uuid4()
    )
    db.add(owner)
    await db.flush()

    institute = InstituteSchema(
        owner_id=owner.id,
        name="Test Institute",
        city="Delhi",
        join_code=_join_code(),
        razorpay_status=RazorpayStatus.CONNECTED,
        razorpay_key_id="rzp_live_abc",
        razorpay_key_secret_encrypted=encrypt_secret("keysecret"),
        razorpay_webhook_secret_encrypted=(
            encrypt_secret(webhook_secret) if webhook_secret else None
        ),
    )
    db.add(institute)
    await db.commit()
    await db.refresh(institute)
    return institute


async def _seed_fee_record(
    db,
    institute,
    payment_link="https://rzp.io/i/abc123",
    amount_due=Decimal("1500.00"),
    amount_paid=Decimal("0"),
    status=FeeStatus.NOT_PAID,
) -> FeeRecordSchema:
    batch = BatchSchema(
        institute_id=institute.id,
        name="Maths Batch",
        subject="Maths",
        start_time=time(9, 0),
        end_time=time(10, 0),
        days_of_week=["MON"],
        max_capacity=30,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )
    db.add(batch)
    await db.flush()

    parent = ParentSchema(
        name="Parent", phone_number=f"8{uuid4().int % 10**9:09d}", institute_id=institute.id
    )
    db.add(parent)
    await db.flush()

    student = StudentSchema(name="Rahul", parent_id=parent.id, institute_id=institute.id)
    db.add(student)
    await db.flush()

    enrollment = EnrollmentSchema(student_id=student.id, batch_id=batch.id, due_day=1, is_active=True)
    db.add(enrollment)
    await db.flush()

    record = FeeRecordSchema(
        enrollment_id=enrollment.id,
        month=date(2026, 6, 1),
        amount_due=amount_due,
        amount_paid=amount_paid,
        status=status,
        payment_link=payment_link,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def _payment_link_paid_payload(
    short_url: str, amount_paid_paise: int, payment_id: str = "pay_test123"
) -> dict:
    return {
        "entity": "event",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_test",
                    "short_url": short_url,
                    "amount_paid": amount_paid_paise,
                    "status": "paid",
                }
            },
            "payment": {"entity": {"id": payment_id, "status": "captured"}},
        },
    }


async def _post_webhook(client, institute_id: int, body: dict, secret: str = WEBHOOK_SECRET):
    body_str = json.dumps(body)
    signature = _sign(body_str, secret)
    return await client.post(
        f"/webhooks/razorpay/{institute_id}",
        content=body_str,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )


# ─── auth / setup errors ────────────────────────────────────────────────────────


async def test_missing_signature_header_returns_400(client):
    response = await client.post(
        "/webhooks/razorpay/1",
        content=json.dumps({"event": "payment_link.paid"}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "X-Razorpay-Signature" in response.json()["detail"]


async def test_unknown_institute_returns_404(client):
    body = _payment_link_paid_payload("https://rzp.io/i/abc123", 150000)
    response = await _post_webhook(client, institute_id=999999, body=body)
    assert response.status_code == 404


async def test_institute_without_webhook_secret_returns_404(client, db_session):
    institute = await _seed_institute(db_session, webhook_secret=None)
    body = _payment_link_paid_payload("https://rzp.io/i/abc123", 150000)

    response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 404


async def test_invalid_signature_returns_400(client, db_session):
    institute = await _seed_institute(db_session)
    body = _payment_link_paid_payload("https://rzp.io/i/abc123", 150000)

    response = await _post_webhook(
        client, institute_id=institute.id, body=body, secret="wrong-secret"
    )

    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


# ─── event handling ──────────────────────────────────────────────────────────


async def test_ignores_events_other_than_payment_link_paid(client, db_session):
    institute = await _seed_institute(db_session)
    body = {"entity": "event", "event": "payment_link.cancelled", "payload": {}}

    response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "event": "payment_link.cancelled"}


async def test_malformed_payload_returns_400(client, db_session):
    institute = await _seed_institute(db_session)
    body = {
        "entity": "event",
        "event": "payment_link.paid",
        "payload": {"payment_link": {"entity": {}}, "payment": {"entity": {}}},
    }

    response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 400


async def test_no_matching_fee_record_is_ignored(client, db_session):
    institute = await _seed_institute(db_session)
    body = _payment_link_paid_payload("https://rzp.io/i/does-not-exist", 150000)

    response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "no matching fee record"}


async def test_already_fully_paid_record_is_idempotent(client, db_session):
    institute = await _seed_institute(db_session)
    record = await _seed_fee_record(
        db_session,
        institute,
        amount_paid=Decimal("1500.00"),
        status=FeeStatus.FULLY_PAID,
    )
    body = _payment_link_paid_payload(record.payment_link, 150000)

    with patch("services.notification_service.send_fee_receipt", new=AsyncMock()) as mock_send:
        response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "note": "already fully paid"}
    mock_send.assert_not_called()


async def test_payment_link_paid_marks_record_fully_paid_and_queues_receipt(client, db_session):
    institute = await _seed_institute(db_session)
    record = await _seed_fee_record(db_session, institute, amount_due=Decimal("1500.00"))
    body = _payment_link_paid_payload(record.payment_link, 150000, payment_id="pay_abc999")

    with patch("services.notification_service.send_fee_receipt", new=AsyncMock()) as mock_send:
        response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    await db_session.refresh(record)
    assert record.status == FeeStatus.FULLY_PAID
    assert record.amount_paid == Decimal("1500.00")
    assert record.payment_reference == "pay_abc999"
    mock_send.assert_called_once()


async def test_partial_webhook_payment_sets_partially_paid(client, db_session):
    institute = await _seed_institute(db_session)
    record = await _seed_fee_record(db_session, institute, amount_due=Decimal("1500.00"))
    # Only part of the outstanding balance was paid on this link
    body = _payment_link_paid_payload(record.payment_link, 50000, payment_id="pay_partial")

    with patch("services.notification_service.send_fee_receipt", new=AsyncMock()) as mock_send:
        response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 200
    await db_session.refresh(record)
    assert record.status == FeeStatus.PARTIALLY_PAID
    assert record.amount_paid == Decimal("500.00")
    mock_send.assert_not_called()


async def test_webhook_payment_adds_to_existing_partial_payment(client, db_session):
    institute = await _seed_institute(db_session)
    record = await _seed_fee_record(
        db_session,
        institute,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("500.00"),
        status=FeeStatus.PARTIALLY_PAID,
    )
    # Payment link was generated for the remaining 1000.00 balance
    body = _payment_link_paid_payload(record.payment_link, 100000, payment_id="pay_rest")

    with patch("services.notification_service.send_fee_receipt", new=AsyncMock()):
        response = await _post_webhook(client, institute_id=institute.id, body=body)

    assert response.status_code == 200
    await db_session.refresh(record)
    assert record.status == FeeStatus.FULLY_PAID
    assert record.amount_paid == Decimal("1500.00")
