"""
Unit tests for services/teacher_service.py.

All repository and Supabase calls are mocked — no DB or network required.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from models.teacher_base import TeacherSchema
from services.teacher_service import TeacherService


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _mock_data(user_id=None, phone="9123456780"):
    user = MagicMock()
    user.id = str(user_id or uuid4())
    user.aud = "authenticated"

    session = MagicMock()
    session.access_token = "tok_abc_1234567890"
    session.refresh_token = "ref_xyz_1234567890"

    data = MagicMock()
    data.user = user
    data.session = session
    return data


# ---------------------------------------------------------------------------
# invite_teacher
# ---------------------------------------------------------------------------


async def test_invite_teacher_creates_record_and_sends_otp():
    svc = TeacherService()
    supabase = _mock_supabase()
    db = MagicMock()

    created_teacher = MagicMock(spec=TeacherSchema)
    created_teacher.id = 1

    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_phone = AsyncMock(return_value=None)
    svc.teacher_repo.create = AsyncMock(return_value=created_teacher)
    svc.teacher_repo.delete = AsyncMock()

    supabase.auth.sign_in_with_otp = AsyncMock(return_value={"message_id": "sms_123"})

    result = await svc.invite_teacher(
        supabase=supabase,
        db=db,
        institute_id=5,
        name="Ravi Kumar",
        phone="9123456780",
    )

    svc.teacher_repo.get_by_phone.assert_called_once_with(db, "9123456780")
    svc.teacher_repo.create.assert_called_once()
    supabase.auth.sign_in_with_otp.assert_called_once_with({"phone": "+919123456780"})
    assert result == created_teacher


async def test_invite_teacher_raises_if_phone_exists():
    svc = TeacherService()
    supabase = _mock_supabase()
    db = MagicMock()

    existing = MagicMock(spec=TeacherSchema)
    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_phone = AsyncMock(return_value=existing)

    with pytest.raises(ValueError, match="already exists"):
        await svc.invite_teacher(
            supabase=supabase, db=db, institute_id=5, name="Ravi", phone="9123456780"
        )


async def test_invite_teacher_rolls_back_on_otp_failure():
    svc = TeacherService()
    supabase = _mock_supabase()
    db = MagicMock()

    created_teacher = MagicMock(spec=TeacherSchema)
    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_phone = AsyncMock(return_value=None)
    svc.teacher_repo.create = AsyncMock(return_value=created_teacher)
    svc.teacher_repo.delete = AsyncMock()

    supabase.auth.sign_in_with_otp = AsyncMock(side_effect=Exception("SMS gateway down"))

    with pytest.raises(ValueError, match="Could not send OTP"):
        await svc.invite_teacher(
            supabase=supabase, db=db, institute_id=5, name="Ravi", phone="9123456780"
        )

    # Rollback: the created teacher should be deleted
    svc.teacher_repo.delete.assert_called_once_with(db, created_teacher)


# ---------------------------------------------------------------------------
# verify_otp
# ---------------------------------------------------------------------------


async def test_verify_otp_links_user_id_to_teacher():
    svc = TeacherService()
    supabase = _mock_supabase()
    db = MagicMock()

    user_id = uuid4()
    otp_data = _mock_data(user_id=user_id)
    supabase.auth.verify_otp = AsyncMock(return_value=otp_data)

    teacher = MagicMock(spec=TeacherSchema)
    teacher.phone_number = "9123456780"

    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_phone = AsyncMock(return_value=teacher)
    svc.teacher_repo.update = AsyncMock(return_value=teacher)

    access_token, refresh_token, aud, returned_uid = await svc.verify_otp(
        supabase=supabase, db=db, phone="9123456780", token="123456"
    )

    supabase.auth.verify_otp.assert_called_once_with({
        "phone": "+919123456780",
        "token": "123456",
        "type": "sms",
    })
    svc.teacher_repo.update.assert_called_once_with(db, teacher, {"user_id": user_id})
    assert access_token == "tok_abc_1234567890"
    assert refresh_token == "ref_xyz_1234567890"
    assert aud == "authenticated"
    assert returned_uid == user_id


async def test_verify_otp_raises_if_no_pending_invite():
    svc = TeacherService()
    supabase = _mock_supabase()
    db = MagicMock()

    otp_data = _mock_data()
    supabase.auth.verify_otp = AsyncMock(return_value=otp_data)

    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_phone = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="No pending teacher invite"):
        await svc.verify_otp(
            supabase=supabase, db=db, phone="9123456780", token="123456"
        )


async def test_verify_otp_raises_on_supabase_error():
    svc = TeacherService()
    supabase = _mock_supabase()
    db = MagicMock()

    supabase.auth.verify_otp = AsyncMock(side_effect=Exception("Token expired"))

    svc.teacher_repo = MagicMock()

    with pytest.raises(ValueError, match="Token expired"):
        await svc.verify_otp(
            supabase=supabase, db=db, phone="9123456780", token="999999"
        )


# ---------------------------------------------------------------------------
# remove_teacher
# ---------------------------------------------------------------------------


async def test_remove_teacher_deletes_record():
    svc = TeacherService()
    db = MagicMock()

    teacher = MagicMock(spec=TeacherSchema)
    teacher.id = 1
    teacher.institute_id = 5

    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_id = AsyncMock(return_value=teacher)
    svc.teacher_repo.delete = AsyncMock()

    await svc.remove_teacher(db=db, institute_id=5, teacher_id=1)

    svc.teacher_repo.delete.assert_called_once_with(db, teacher)


async def test_remove_teacher_raises_if_not_found():
    svc = TeacherService()
    db = MagicMock()

    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Teacher not found"):
        await svc.remove_teacher(db=db, institute_id=5, teacher_id=99)


async def test_remove_teacher_raises_if_wrong_institute():
    svc = TeacherService()
    db = MagicMock()

    teacher = MagicMock(spec=TeacherSchema)
    teacher.id = 1
    teacher.institute_id = 999  # Different institute

    svc.teacher_repo = MagicMock()
    svc.teacher_repo.get_by_id = AsyncMock(return_value=teacher)

    with pytest.raises(ValueError, match="does not belong"):
        await svc.remove_teacher(db=db, institute_id=5, teacher_id=1)
