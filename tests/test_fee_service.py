"""
Unit tests for services/fee_service.py.

All repository and DB calls are mocked — no DB or network required.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema
from services.fee_service import FeeService, PaymentMethod


def _make_structure(structure_id=1, batch_id=10, monthly_amount=Decimal("1500.00")):
    s = MagicMock(spec=FeeStructureSchema)
    s.id = structure_id
    s.batch_id = batch_id
    s.monthly_amount = monthly_amount
    s.created_at = datetime(2026, 1, 1)
    return s


def _make_fee_record(
    record_id=1,
    enrollment_id=5,
    month=date(2026, 5, 1),
    amount_due=Decimal("1500.00"),
    amount_paid=Decimal("0"),
    status=FeeStatus.NOT_PAID,
):
    r = MagicMock(spec=FeeRecordSchema)
    r.id = record_id
    r.enrollment_id = enrollment_id
    r.month = month
    r.amount_due = amount_due
    r.amount_paid = amount_paid
    r.status = status
    r.paid_at = None
    r.payment_reference = None
    r.payment_link = None
    r.created_at = datetime(2026, 5, 1)
    return r


def _make_enrollment(enrollment_id=5, batch_id=10, is_active=True, first_month_amount=None):
    from models.enrollment_base import EnrollmentSchema

    e = MagicMock(spec=EnrollmentSchema)
    e.id = enrollment_id
    e.batch_id = batch_id
    e.is_active = is_active
    e.first_month_amount = first_month_amount
    return e


# ---------------------------------------------------------------------------
# setup_fee_structure
# ---------------------------------------------------------------------------


async def test_setup_fee_structure_creates_structure():
    svc = FeeService()
    db = MagicMock()
    structure = _make_structure()

    svc.fee_repo = MagicMock()
    svc.fee_repo.create_or_update_structure = AsyncMock(return_value=structure)

    result = await svc.setup_fee_structure(db=db, batch_id=10, monthly_amount=Decimal("1500.00"))

    svc.fee_repo.create_or_update_structure.assert_called_once_with(
        db, 10, Decimal("1500.00")
    )
    assert result == structure


async def test_setup_fee_structure_raises_on_zero_amount():
    svc = FeeService()
    db = MagicMock()

    with pytest.raises(ValueError, match="greater than 0"):
        await svc.setup_fee_structure(db=db, batch_id=10, monthly_amount=Decimal("0"))


async def test_setup_fee_structure_raises_on_negative_amount():
    svc = FeeService()
    db = MagicMock()

    with pytest.raises(ValueError, match="greater than 0"):
        await svc.setup_fee_structure(db=db, batch_id=10, monthly_amount=Decimal("-100"))


# ---------------------------------------------------------------------------
# generate_monthly_records
# ---------------------------------------------------------------------------


async def test_generate_monthly_records_creates_records_for_active_enrollments():
    svc = FeeService()
    db = MagicMock()

    structure = _make_structure(monthly_amount=Decimal("1500.00"))
    e1 = _make_enrollment(enrollment_id=1)
    e2 = _make_enrollment(enrollment_id=2)
    record1 = _make_fee_record(record_id=1, enrollment_id=1)
    record2 = _make_fee_record(record_id=2, enrollment_id=2)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_structure_by_batch = AsyncMock(return_value=structure)
    svc.fee_repo.get_record_by_enrollment_and_month = AsyncMock(return_value=None)
    svc.fee_repo.bulk_create_records = AsyncMock(return_value=[record1, record2])

    # Mock the DB execute call for active enrollments
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [e1, e2]
    db.execute = AsyncMock(return_value=mock_result)

    month = date(2026, 5, 1)
    result = await svc.generate_monthly_records(db=db, batch_id=10, month=month)

    svc.fee_repo.bulk_create_records.assert_called_once()
    call_args = svc.fee_repo.bulk_create_records.call_args[0]
    new_records = call_args[1]
    assert len(new_records) == 2
    assert all(r.amount_due == Decimal("1500.00") for r in new_records)
    assert all(r.status == FeeStatus.NOT_PAID for r in new_records)


async def test_generate_monthly_records_raises_when_no_structure():
    svc = FeeService()
    db = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_structure_by_batch = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="No FeeStructure found"):
        await svc.generate_monthly_records(db=db, batch_id=10, month=date(2026, 5, 1))


async def test_generate_monthly_records_skips_existing():
    """Enrollments that already have a record for the month are skipped."""
    svc = FeeService()
    db = MagicMock()

    structure = _make_structure()
    e1 = _make_enrollment(enrollment_id=1)
    existing_record = _make_fee_record(enrollment_id=1)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_structure_by_batch = AsyncMock(return_value=structure)
    svc.fee_repo.get_record_by_enrollment_and_month = AsyncMock(return_value=existing_record)
    svc.fee_repo.bulk_create_records = AsyncMock(return_value=[])

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [e1]
    db.execute = AsyncMock(return_value=mock_result)

    result = await svc.generate_monthly_records(db=db, batch_id=10, month=date(2026, 5, 1))

    # bulk_create_records should not be called since there's nothing new to create
    svc.fee_repo.bulk_create_records.assert_not_called()
    assert result == []


async def test_generate_monthly_records_uses_first_month_amount():
    """When enrollment.first_month_amount is set, use it instead of structure amount."""
    svc = FeeService()
    db = MagicMock()

    structure = _make_structure(monthly_amount=Decimal("1500.00"))
    e1 = _make_enrollment(enrollment_id=1, first_month_amount=Decimal("750.00"))
    record1 = _make_fee_record(record_id=1, enrollment_id=1, amount_due=Decimal("750.00"))

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_structure_by_batch = AsyncMock(return_value=structure)
    svc.fee_repo.get_record_by_enrollment_and_month = AsyncMock(return_value=None)
    svc.fee_repo.bulk_create_records = AsyncMock(return_value=[record1])

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [e1]
    db.execute = AsyncMock(return_value=mock_result)

    await svc.generate_monthly_records(db=db, batch_id=10, month=date(2026, 5, 1))

    call_args = svc.fee_repo.bulk_create_records.call_args[0]
    new_records = call_args[1]
    assert len(new_records) == 1
    assert new_records[0].amount_due == Decimal("750.00")


async def test_generate_monthly_records_no_active_enrollments():
    """If there are no active enrollments, nothing is created."""
    svc = FeeService()
    db = MagicMock()

    structure = _make_structure()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_structure_by_batch = AsyncMock(return_value=structure)
    svc.fee_repo.bulk_create_records = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    result = await svc.generate_monthly_records(db=db, batch_id=10, month=date(2026, 5, 1))

    svc.fee_repo.bulk_create_records.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# mark_payment
# ---------------------------------------------------------------------------


async def test_mark_payment_full_amount_sets_fully_paid():
    svc = FeeService()
    db = MagicMock()

    original = _make_fee_record(amount_due=Decimal("1500.00"), amount_paid=Decimal("0"))
    updated = _make_fee_record(
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("1500.00"),
        status=FeeStatus.FULLY_PAID,
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=original)
    svc.fee_repo.update_payment = AsyncMock(return_value=updated)

    result = await svc.mark_payment(
        db=db, record_id=1, amount_paid=Decimal("1500.00"), reference="UPI123"
    )

    svc.fee_repo.update_payment.assert_called_once_with(
        db, original, Decimal("1500.00"), "UPI123"
    )
    assert result == updated


async def test_mark_payment_partial_amount_sets_partially_paid():
    svc = FeeService()
    db = MagicMock()

    original = _make_fee_record(amount_due=Decimal("1500.00"), amount_paid=Decimal("0"))
    updated = _make_fee_record(
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("500.00"),
        status=FeeStatus.PARTIALLY_PAID,
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=original)
    svc.fee_repo.update_payment = AsyncMock(return_value=updated)

    result = await svc.mark_payment(
        db=db, record_id=1, amount_paid=Decimal("500.00")
    )

    assert result == updated


async def test_mark_payment_zero_amount_resets_to_not_paid():
    svc = FeeService()
    db = MagicMock()

    original = _make_fee_record(
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("500.00"),
        status=FeeStatus.PARTIALLY_PAID,
    )
    updated = _make_fee_record(
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=original)
    svc.fee_repo.update_payment = AsyncMock(return_value=updated)

    result = await svc.mark_payment(db=db, record_id=1, amount_paid=Decimal("0"))

    assert result == updated


async def test_mark_payment_raises_when_record_not_found():
    svc = FeeService()
    db = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="FeeRecord 99 not found"):
        await svc.mark_payment(db=db, record_id=99, amount_paid=Decimal("100"))


async def test_mark_payment_raises_on_negative_amount():
    svc = FeeService()
    db = MagicMock()

    record = _make_fee_record()
    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)

    with pytest.raises(ValueError, match="cannot be negative"):
        await svc.mark_payment(db=db, record_id=1, amount_paid=Decimal("-10"))


async def test_mark_payment_overpayment_sets_fully_paid():
    """Overpayment (amount_paid > amount_due) should still set FULLY_PAID."""
    svc = FeeService()
    db = MagicMock()

    original = _make_fee_record(amount_due=Decimal("1500.00"))
    updated = _make_fee_record(
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("2000.00"),
        status=FeeStatus.FULLY_PAID,
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=original)
    svc.fee_repo.update_payment = AsyncMock(return_value=updated)

    result = await svc.mark_payment(
        db=db, record_id=1, amount_paid=Decimal("2000.00")
    )

    assert result == updated


# ---------------------------------------------------------------------------
# generate_payment_link
# ---------------------------------------------------------------------------


async def test_generate_payment_link_success():
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=1,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/test123"})

    result = await svc.generate_payment_link(db=db, record_id=1, razorpay_client=razorpay_client)

    assert result["payment_link"] == "https://rzp.io/i/test123"
    assert result["amount_pending"] == Decimal("1500.00")
    assert result["record_id"] == 1
    assert result["month"] == date(2026, 5, 1)
    svc.fee_repo.update_payment_link.assert_called_once_with(
        db, record, "https://rzp.io/i/test123"
    )


async def test_generate_payment_link_partial_pending_amount():
    """Link covers the remaining balance, not the full fee."""
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=2,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("500.00"),
        status=FeeStatus.PARTIALLY_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/partial"})

    result = await svc.generate_payment_link(db=db, record_id=2, razorpay_client=razorpay_client)

    assert result["amount_pending"] == Decimal("1000.00")
    # Verify Razorpay received the correct paise amount (₹1000 = 100000 paise)
    _, data_sent = svc._create_razorpay_link.call_args.args
    assert data_sent["amount"] == 100000


async def test_generate_payment_link_defaults_to_upi_link():
    """Without an explicit payment_method, a UPI-only link is created."""
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=3,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/upi123"})

    await svc.generate_payment_link(db=db, record_id=3, razorpay_client=razorpay_client)

    _, data_sent = svc._create_razorpay_link.call_args.args
    assert data_sent["upi_link"] == "true"


async def test_generate_payment_link_explicit_upi_link():
    """payment_method=PaymentMethod.UPI explicitly also creates a UPI-only link."""
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=4,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/upi456"})

    await svc.generate_payment_link(
        db=db, record_id=4, razorpay_client=razorpay_client, payment_method=PaymentMethod.UPI
    )

    _, data_sent = svc._create_razorpay_link.call_args.args
    assert data_sent["upi_link"] == "true"


async def test_generate_payment_link_standard_when_payment_method_none():
    """payment_method=None generates today's standard (all-methods) payment link."""
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=5,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/standard"})

    await svc.generate_payment_link(
        db=db, record_id=5, razorpay_client=razorpay_client, payment_method=None
    )

    _, data_sent = svc._create_razorpay_link.call_args.args
    assert "upi_link" not in data_sent


async def test_generate_payment_link_includes_callback_url():
    """callback_url/callback_method route the payer back to the success page."""
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=6,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/cb"})

    with patch("services.fee_service.get_settings") as mock_settings:
        mock_settings.return_value.frontend_base_url = "https://batchbook.in"
        await svc.generate_payment_link(db=db, record_id=6, razorpay_client=razorpay_client)

    _, data_sent = svc._create_razorpay_link.call_args.args
    assert data_sent["callback_url"] == "https://batchbook.in/payment-success"
    assert data_sent["callback_method"] == "get"


async def test_generate_payment_link_raises_when_record_not_found():
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="FeeRecord 99 not found"):
        await svc.generate_payment_link(db=db, record_id=99, razorpay_client=razorpay_client)


async def test_generate_payment_link_raises_when_already_fully_paid():
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("1500.00"),
        status=FeeStatus.FULLY_PAID,
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)

    with pytest.raises(ValueError, match="already fully paid"):
        await svc.generate_payment_link(db=db, record_id=1, razorpay_client=razorpay_client)


# ---------------------------------------------------------------------------
# backfill_missing_payment_links
# ---------------------------------------------------------------------------


def _make_backfill_institute(institute_id=10, status=None):
    from models.institute_base import InstituteSchema, RazorpayStatus

    i = MagicMock(spec=InstituteSchema)
    i.id = institute_id
    i.razorpay_status = status or RazorpayStatus.CONNECTED
    i.razorpay_key_id = "rzp_live_abc"
    i.razorpay_key_secret_encrypted = "enc-blob"
    return i


async def test_backfill_generates_links_for_connected_institute():
    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute()
    record1 = _make_fee_record(record_id=1)
    record2 = _make_fee_record(record_id=2)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(record1, institute), (record2, institute)]
    )
    svc.generate_payment_link = AsyncMock(return_value={})

    with patch("clients.razorpay_client.build_institute_razorpay_client", return_value=MagicMock()):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["checked"] == 2
    assert summary["generated"] == 2
    assert summary["skipped_no_razorpay"] == 0
    assert summary["failed"] == 0
    assert svc.generate_payment_link.call_count == 2


async def test_backfill_skips_institutes_without_razorpay_connected():
    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute()
    record1 = _make_fee_record(record_id=1)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(record1, institute)]
    )
    svc.generate_payment_link = AsyncMock()

    with patch("clients.razorpay_client.build_institute_razorpay_client", return_value=None):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["skipped_no_razorpay"] == 1
    assert summary["generated"] == 0
    svc.generate_payment_link.assert_not_called()


async def test_backfill_isolates_client_build_failure_to_one_institute():
    """A broken Razorpay client for one institute must not abort the whole batch."""
    svc = FeeService()
    db = MagicMock()

    broken_institute = _make_backfill_institute(institute_id=10)
    healthy_institute = _make_backfill_institute(institute_id=20)
    broken_record = _make_fee_record(record_id=1)
    healthy_record = _make_fee_record(record_id=2)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(broken_record, broken_institute), (healthy_record, healthy_institute)]
    )
    svc.generate_payment_link = AsyncMock(return_value={})

    with patch(
        "clients.razorpay_client.build_institute_razorpay_client",
        side_effect=[ValueError("Could not decrypt stored secret — key may have changed"), MagicMock()],
    ):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["skipped_no_razorpay"] == 1
    assert summary["generated"] == 1
    assert summary["errors"] == [
        {"record_id": 1, "error": "Could not decrypt stored secret — key may have changed"}
    ]
    svc.generate_payment_link.assert_called_once()


async def test_backfill_counts_failures_without_stopping_the_batch():
    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute()
    record1 = _make_fee_record(record_id=1)
    record2 = _make_fee_record(record_id=2)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(record1, institute), (record2, institute)]
    )
    svc.generate_payment_link = AsyncMock(side_effect=[RuntimeError("razorpay down"), {}])

    with patch("clients.razorpay_client.build_institute_razorpay_client", return_value=MagicMock()):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["failed"] == 1
    assert summary["generated"] == 1
    assert summary["errors"] == [{"record_id": 1, "error": "razorpay down"}]


async def test_backfill_defaults_month_to_last_calendar_month():
    svc = FeeService()
    db = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(return_value=[])

    today = date.today()
    first_of_this_month = today.replace(day=1)
    expected_month = (first_of_this_month - timedelta(days=1)).replace(day=1)

    summary = await svc.backfill_missing_payment_links(db=db, institute_id=None, month=None)

    svc.fee_repo.get_records_missing_payment_link_for_month.assert_called_once_with(
        db, expected_month, None
    )
    assert summary["month"] == expected_month


async def test_backfill_passes_institute_id_filter_through():
    svc = FeeService()
    db = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(return_value=[])

    await svc.backfill_missing_payment_links(db=db, institute_id=42, month=date(2026, 6, 1))

    svc.fee_repo.get_records_missing_payment_link_for_month.assert_called_once_with(
        db, date(2026, 6, 1), 42
    )
