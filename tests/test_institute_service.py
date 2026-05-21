"""
Tests for services/institute_service.py — InstituteService.

Symbols under test:
  Class:services/institute_service.py:InstituteService
    create_institute, get_institute_by_owner_id, update_institute
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.institute_base import InstituteSchema
from services.institute_service import InstituteService


@pytest.fixture
def service():
    return InstituteService()


@pytest.fixture
def mock_db():
    return AsyncMock()


def _make_institute(owner_id: int = 1) -> MagicMock:
    inst = MagicMock(spec=InstituteSchema)
    inst.id = 10
    inst.owner_id = owner_id
    inst.name = "Sharma Classes"
    inst.city = "Gurugram"
    return inst


# --- create_institute ---

async def test_create_institute_returns_new_institute(service, mock_db):
    expected = _make_institute(owner_id=5)
    create_mock = AsyncMock(return_value=expected)

    with patch.object(service.institute_repo, "create", new=create_mock):
        result = await service.create_institute(mock_db, owner_id=5, name="Sharma Classes", city="Gurugram")

    assert result is expected
    create_mock.assert_called_once()


async def test_create_institute_builds_correct_schema(service, mock_db):
    create_mock = AsyncMock(return_value=_make_institute())
    captured = {}

    async def capture_create(db, institute):
        captured["institute"] = institute
        return institute

    with patch.object(service.institute_repo, "create", new=AsyncMock(side_effect=capture_create)):
        await service.create_institute(mock_db, owner_id=7, name="Test Academy", city="Lucknow")

    inst = captured["institute"]
    assert inst.owner_id == 7
    assert inst.name == "Test Academy"
    assert inst.city == "Lucknow"


# --- get_institute_by_owner_id ---

async def test_get_institute_by_owner_id_returns_institute(service, mock_db):
    expected = _make_institute(owner_id=3)

    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=expected)):
        result = await service.get_institute_by_owner_id(mock_db, owner_id=3)

    assert result is expected


async def test_get_institute_by_owner_id_returns_none_when_missing(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        result = await service.get_institute_by_owner_id(mock_db, owner_id=999)

    assert result is None


# --- update_institute ---

async def test_update_institute_applies_changes(service, mock_db):
    existing = _make_institute(owner_id=2)
    updated = _make_institute(owner_id=2)
    updated.city = "Mumbai"
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.update_institute(mock_db, owner_id=2, updates={"city": "Mumbai"})

    assert result is updated
    update_mock.assert_called_once_with(mock_db, existing, {"city": "Mumbai"})


async def test_update_institute_returns_none_when_not_found(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        result = await service.update_institute(mock_db, owner_id=999, updates={"city": "Delhi"})

    assert result is None
