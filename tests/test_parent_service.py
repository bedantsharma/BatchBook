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

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from DTO.student_model import StudentFeesStatus
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from repositories.parent_repository import ParentRepository
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
    service.parent_repo.get_by_phone = AsyncMock(return_value=None)
    service.parent_repo.create_parent = AsyncMock(return_value=new_parent)

    result = await service.get_or_create_after_otp(
        db=MagicMock(), user_id=user_id, phone="9876543210", name="New Parent"
    )
    assert result is new_parent
    service.parent_repo.create_parent.assert_called_once()


# --- verify_otp ---

async def test_verify_otp_returns_token_parent_name_and_children_on_success(service):
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
    parent.name = "Test Parent"
    child = _make_student_schema(parent_id=parent.id)
    child.email = "child@test.com"

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)
    service.parent_repo.get_by_phone = AsyncMock(return_value=None)
    service.parent_repo.create_parent = AsyncMock(return_value=parent)
    service.parent_repo.get_students_by_parent_id = AsyncMock(return_value=[child])

    (
        access_token,
        refresh_token,
        aud,
        returned_user_id,
        parent_name,
        children,
    ) = await service.verify_otp(
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
    assert parent_name == "Test Parent"
    assert len(children) == 1
    assert children[0].email == "child@test.com"


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


# --- TDD tests: stub-claim + name persistence (Task 4) ---


@pytest.mark.asyncio
async def test_claims_stub_by_phone_and_sets_name(db_session: AsyncSession):
    # Owner-created stub: phone + name, no user_id
    repo = ParentRepository()
    stub = ParentSchema(phone_number="9876543210", name="Asha", user_id=None)
    await repo.create_parent(db_session, stub)

    uid = uuid.uuid4()
    svc = ParentService()
    parent = await svc.get_or_create_after_otp(
        db_session, uid, "9876543210", name="Asha Devi"
    )

    assert parent.id == stub.id  # same row claimed, not a duplicate
    assert str(parent.user_id) == str(uid)
    assert parent.name == "Asha Devi"  # name updated from OTP step


@pytest.mark.asyncio
async def test_creates_new_parent_when_none_exists(db_session: AsyncSession):
    uid = uuid.uuid4()
    svc = ParentService()
    parent = await svc.get_or_create_after_otp(db_session, uid, "9000000000", name="New")
    assert parent.id is not None
    assert parent.name == "New"


@pytest.mark.asyncio
async def test_backfills_name_on_existing_verified_parent(db_session: AsyncSession):
    uid = uuid.uuid4()
    repo = ParentRepository()
    existing = ParentSchema(phone_number="9111111111", name=None, user_id=uid)
    await repo.create_parent(db_session, existing)

    svc = ParentService()
    parent = await svc.get_or_create_after_otp(
        db_session, uid, "9111111111", name="Filled"
    )
    assert parent.name == "Filled"


# --- update_child ---

async def test_update_child_applies_changes_when_owned(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    student = _make_student_schema(parent_id=parent.id)
    updated_student = _make_student_schema(parent_id=parent.id)
    updated_student.email = "new@test.com"

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.student_repo = MagicMock()
    service.student_repo.get_by_id = AsyncMock(return_value=student)
    service.student_repo.update_student = AsyncMock(return_value=updated_student)

    result = await service.update_child(
        db=MagicMock(), user_id=user_id, student_id=student.id, updates={"email": "new@test.com"}
    )
    assert result.email == "new@test.com"


async def test_update_child_raises_permission_error_when_not_owned(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    other_parents_student = _make_student_schema(parent_id=999)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.student_repo = MagicMock()
    service.student_repo.get_by_id = AsyncMock(return_value=other_parents_student)

    with pytest.raises(PermissionError):
        await service.update_child(
            db=MagicMock(), user_id=user_id, student_id=999, updates={"email": "x@test.com"}
        )


async def test_update_child_returns_none_when_student_not_found(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.student_repo = MagicMock()
    service.student_repo.get_by_id = AsyncMock(return_value=None)

    result = await service.update_child(
        db=MagicMock(), user_id=user_id, student_id=404, updates={"email": "x@test.com"}
    )
    assert result is None


async def test_update_child_returns_none_when_parent_not_found(service):
    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)
    service.student_repo = MagicMock()

    result = await service.update_child(
        db=MagicMock(), user_id=uuid4(), student_id=1, updates={"email": "x@test.com"}
    )
    assert result is None
    service.student_repo.get_by_id.assert_not_called()
