"""
Tests for services/auth_service.py — get_current_user_id.

Symbols under test (from GitNexus):
  Function:services/auth_service.py:get_current_user_id
  Called by: StudentService.get_current_user_id, OwnerService.get_current_teacher_id
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from services.auth_service import get_current_user_id


@pytest.fixture
def mock_supabase():
    supabase = MagicMock()
    supabase.auth = MagicMock()
    return supabase


async def test_get_current_user_id_strips_bearer_prefix(mock_supabase):
    user_id = uuid4()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=MagicMock(user=MagicMock(id=str(user_id)))
    )

    result = await get_current_user_id(mock_supabase, f"Bearer {user_id}")

    mock_supabase.auth.get_user.assert_called_once_with(str(user_id))
    assert result == user_id


async def test_get_current_user_id_returns_uuid(mock_supabase):
    user_id = uuid4()
    mock_supabase.auth.get_user = AsyncMock(
        return_value=MagicMock(user=MagicMock(id=str(user_id)))
    )

    result = await get_current_user_id(mock_supabase, f"Bearer sometoken")

    assert isinstance(result, UUID)


async def test_get_current_user_id_raises_on_invalid_token(mock_supabase):
    mock_supabase.auth.get_user = AsyncMock(side_effect=Exception("Invalid JWT"))

    with pytest.raises(Exception, match="Invalid JWT"):
        await get_current_user_id(mock_supabase, "Bearer badtoken")
