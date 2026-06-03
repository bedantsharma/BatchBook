"""
Tests for services/owner_service.py — OwnerService.

Symbols under test (from GitNexus):
  Class:services/owner_service.py:OwnerService
    get_or_create_after_otp, verify_otp, get_current_teacher_id,
    get_owner_by_teacher_id, update_owner
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.owner_base import OwnerSchema
from services.owner_service import OwnerService


@pytest.fixture
def service():
    return OwnerService()


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_supabase():
    supabase = MagicMock()
    supabase.auth = MagicMock()
    return supabase


def _make_owner_schema(teacher_id=None, phone="9876543210"):
    schema = MagicMock(spec=OwnerSchema)
    schema.teacher_id = teacher_id or uuid4()
    schema.phone_number = phone
    schema.name = "Test Owner"
    schema.email = "test@example.com"
    return schema


# --- get_or_create_after_otp ---

async def test_get_or_create_returns_existing_owner(service, mock_db):
    teacher_id = uuid4()
    existing = _make_owner_schema(teacher_id=teacher_id)

    with patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=existing)):
        result = await service.get_or_create_after_otp(mock_db, teacher_id, "9876543210", "Alice", None)

    assert result is existing


async def test_get_or_create_creates_new_owner_when_not_found(service, mock_db):
    teacher_id = uuid4()
    new_owner = _make_owner_schema(teacher_id=teacher_id)
    create_mock = AsyncMock(return_value=new_owner)

    with (
        patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=None)),
        patch.object(service.owner_repo, "get_by_phone", new=AsyncMock(return_value=None)),
        patch.object(service.owner_repo, "create_owner", new=create_mock),
    ):
        result = await service.get_or_create_after_otp(mock_db, teacher_id, "9876543210", "Alice", "a@b.com")
        assert result is new_owner
        create_mock.assert_called_once()


async def test_get_or_create_updates_teacher_id_when_phone_exists_with_different_uuid(service, mock_db):
    """Handles re-registration after Supabase account wipe: same phone, new UUID."""
    old_teacher_id = uuid4()
    new_teacher_id = uuid4()
    existing_by_phone = _make_owner_schema(teacher_id=old_teacher_id)
    updated = _make_owner_schema(teacher_id=new_teacher_id)
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=None)),
        patch.object(service.owner_repo, "get_by_phone", new=AsyncMock(return_value=existing_by_phone)),
        patch.object(service.owner_repo, "update_owner", new=update_mock),
    ):
        result = await service.get_or_create_after_otp(mock_db, new_teacher_id, "9876543210", "Alice", None)
        assert result is updated
        update_mock.assert_called_once_with(mock_db, existing_by_phone, {"teacher_id": new_teacher_id})


# --- verify_otp ---

async def test_verify_otp_returns_token_aud_and_teacher_id(service, mock_db, mock_supabase):
    teacher_id = uuid4()
    mock_supabase.auth.verify_otp = AsyncMock(return_value=MagicMock(
        user=MagicMock(id=str(teacher_id), aud="authenticated"),
        session=MagicMock(access_token="tok_abc123", refresh_token="ref_xyz789"),
    ))

    with patch.object(service, "get_or_create_after_otp", new=AsyncMock()):
        token, refresh_token, aud, tid = await service.verify_otp(mock_supabase, mock_db, "9876543210", "123456", "Alice", None)

    assert token == "tok_abc123"
    assert refresh_token == "ref_xyz789"
    assert aud == "authenticated"
    assert tid == teacher_id


async def test_verify_otp_raises_value_error_on_missing_user(service, mock_db, mock_supabase):
    mock_supabase.auth.verify_otp = AsyncMock(return_value=MagicMock(user=None, session=None))

    with pytest.raises(ValueError, match="OTP verification failed"):
        await service.verify_otp(mock_supabase, mock_db, "9876543210", "wrong", None, None)


# --- get_current_teacher_id ---

async def test_get_current_teacher_id_delegates_to_auth_service(service, mock_supabase):
    teacher_id = uuid4()

    with patch("services.owner_service.get_current_user_id", new=AsyncMock(return_value=teacher_id)) as mock_auth:
        result = await service.get_current_teacher_id(mock_supabase, "Bearer sometoken")

    assert result == teacher_id
    mock_auth.assert_called_once_with(mock_supabase, "Bearer sometoken")


# --- get_owner_by_teacher_id ---

async def test_get_owner_by_teacher_id_returns_owner(service, mock_db):
    teacher_id = uuid4()
    owner = _make_owner_schema(teacher_id=teacher_id)

    with patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=owner)):
        result = await service.get_owner_by_teacher_id(mock_db, teacher_id)

    assert result is owner


async def test_get_owner_by_teacher_id_returns_none_when_missing(service, mock_db):
    with patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=None)):
        result = await service.get_owner_by_teacher_id(mock_db, uuid4())

    assert result is None


# --- update_owner ---

async def test_update_owner_applies_changes(service, mock_db):
    teacher_id = uuid4()
    owner = _make_owner_schema(teacher_id=teacher_id)
    updated = _make_owner_schema(teacher_id=teacher_id)
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=owner)),
        patch.object(service.owner_repo, "update_owner", new=update_mock),
    ):
        result = await service.update_owner(mock_db, teacher_id, {"city": "Delhi"})
        assert result is updated
        update_mock.assert_called_once_with(mock_db, owner, {"city": "Delhi"})


async def test_update_owner_returns_none_when_owner_not_found(service, mock_db):
    with patch.object(service.owner_repo, "get_by_teacher_id", new=AsyncMock(return_value=None)):
        result = await service.update_owner(mock_db, uuid4(), {"city": "Delhi"})

    assert result is None
