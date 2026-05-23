"""
Tests for services/parent_service.py

Covers:
- get_or_create_after_otp: returns existing parent; creates new when not found
- verify_otp: returns (access_token, refresh_token, aud, user_id, children) on success
- verify_otp: raises ValueError when supabase returns no user/session
- get_current_user_id: delegates to auth_service
- get_children: returns children for known parent, empty list for unknown
- update_parent: applies changes; returns None when parent not found
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from DTO.student_model import StudentFeesStatus
from services.parent_service import ParentService


def _make_parent_schema(user_id=None, phone="9876543210"):
    p = MagicMock(spec=ParentSchema)
    p.id = 1
    p.user_id = user_id or uuid4()
    p.phone_number = phone
    p.name = "Test Parent"
    p.created_at = datetime(2026, 1, 1)
    return p


def _make_student_schema(parent_id: int = 1):
    s = MagicMock(spec=StudentSchema)
    s.id = 1
    s.name = "Test Child"
    s.fees_status = StudentFeesStatus.NOT_PAID
    s.parent_id = parent_id
    s.institute_id = None
    s.email = None
    return s


@pytest.fixture
def service():
    return ParentService()


# --- get_or_create_after_otp ---

async def test_get_or_create_returns_existing_parent(service):
    user_id = uuid4()
    existing_parent = _make_parent_schema(user_id=user_id)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=existing_parent)

    result = await service.get_or_create_after_otp(
        db=MagicMock(), user_id=user_id, phone="9876543210", name="Test Parent"
    )
    assert result is existing_parent
    service.parent_repo.create_parent.assert_not_called()


async def test_get_or_create_creates_new_parent_when_not_found(service):
    user_id = uuid4()
    new_parent = _make_parent_schema(user_id=user_id)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)
    service.parent_repo.create_parent = AsyncMock(return_value=new_parent)

    result = await service.get_or_create_after_otp(
        db=MagicMock(), user_id=user_id, phone="9876543210", name="New Parent"
    )
    assert result is new_parent
    service.parent_repo.create_parent.assert_called_once()


# --- verify_otp ---

async def test_verify_otp_returns_token_and_children_on_success(service):
    user_id = uuid4()
    mock_user = MagicMock()
    mock_user.id = str(user_id)
    mock_user.aud = "authenticated"

    mock_session = MagicMock()
    mock_session.access_token = "access_tok_1234567890"
    mock_session.refresh_token = "refresh_tok_1234567890"

    mock_data = MagicMock()
    mock_data.user = mock_user
    mock_data.session = mock_session

    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp = AsyncMock(return_value=mock_data)

    parent = _make_parent_schema(user_id=user_id)
    child = _make_student_schema(parent_id=parent.id)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)
    service.parent_repo.create_parent = AsyncMock(return_value=parent)
    service.parent_repo.get_students_by_parent_id = AsyncMock(return_value=[child])

    access_token, refresh_token, aud, returned_user_id, children = await service.verify_otp(
        supabase=mock_supabase,
        db=MagicMock(),
        phone="9876543210",
        token="123456",
        name="Test Parent",
    )

    assert access_token == "access_tok_1234567890"
    assert refresh_token == "refresh_tok_1234567890"
    assert aud == "authenticated"
    assert returned_user_id == user_id
    assert len(children) == 1


async def test_verify_otp_raises_value_error_when_no_user(service):
    mock_data = MagicMock()
    mock_data.user = None
    mock_data.session = None

    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp = AsyncMock(return_value=mock_data)

    with pytest.raises(ValueError, match="OTP verification failed"):
        await service.verify_otp(
            supabase=mock_supabase,
            db=MagicMock(),
            phone="9876543210",
            token="000000",
            name=None,
        )


async def test_verify_otp_raises_value_error_on_supabase_exception(service):
    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp = AsyncMock(side_effect=Exception("Supabase error"))

    with pytest.raises(ValueError):
        await service.verify_otp(
            supabase=mock_supabase,
            db=MagicMock(),
            phone="9876543210",
            token="000000",
            name=None,
        )


# --- get_current_user_id ---

async def test_get_current_user_id_delegates_to_auth_service(service):
    user_id = uuid4()
    with patch("services.parent_service.get_current_user_id", new_callable=AsyncMock) as mock_auth:
        mock_auth.return_value = user_id
        result = await service.get_current_user_id(
            supabase=MagicMock(), authorization="Bearer some_token"
        )
    assert result == user_id


# --- get_children ---

async def test_get_children_returns_children_for_known_parent(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    child = _make_student_schema(parent_id=parent.id)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.parent_repo.get_students_by_parent_id = AsyncMock(return_value=[child])

    children = await service.get_children(db=MagicMock(), user_id=user_id)
    assert len(children) == 1


async def test_get_children_returns_empty_list_when_parent_not_found(service):
    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)

    children = await service.get_children(db=MagicMock(), user_id=uuid4())
    assert children == []


# --- update_parent ---

async def test_update_parent_applies_changes(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    updated = _make_parent_schema(user_id=user_id)
    updated.name = "Updated Name"

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.parent_repo.update_parent = AsyncMock(return_value=updated)

    result = await service.update_parent(
        db=MagicMock(), user_id=user_id, updates={"name": "Updated Name"}
    )
    assert result.name == "Updated Name"


async def test_update_parent_returns_none_when_parent_not_found(service):
    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)

    result = await service.update_parent(
        db=MagicMock(), user_id=uuid4(), updates={"name": "Ghost"}
    )
    assert result is None
