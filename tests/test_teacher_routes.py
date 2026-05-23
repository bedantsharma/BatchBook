"""
Tests for routes/teacher_route.py — all HTTP endpoints.

Supabase, OwnerService, InstituteService, and TeacherService are mocked
so no real network or database calls are made.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.teacher_base import TeacherSchema
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service
from services.teacher_service import TeacherService, get_teacher_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_owner(teacher_id=None, owner_id=1):
    owner = MagicMock(spec=OwnerSchema)
    owner.id = owner_id
    owner.teacher_id = teacher_id or uuid4()
    owner.phone_number = "9876543210"
    owner.name = "Sharma Sir"
    return owner


def _make_institute(owner_id=1, institute_id=10):
    inst = MagicMock(spec=InstituteSchema)
    inst.id = institute_id
    inst.owner_id = owner_id
    inst.name = "Sharma Classes"
    inst.city = "Delhi"
    inst.created_at = datetime(2026, 1, 1)
    return inst


def _make_teacher(teacher_id=None, user_id=None, institute_id=10):
    t = MagicMock(spec=TeacherSchema)
    t.id = teacher_id or 1
    t.institute_id = institute_id
    t.name = "Ravi Kumar"
    t.phone_number = "9123456780"
    t.user_id = user_id or uuid4()
    t.created_at = datetime(2026, 1, 1)
    return t


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = _mock_supabase()
    from app import app

    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


# ---------------------------------------------------------------------------
# POST /teacher/invite
# ---------------------------------------------------------------------------


async def test_invite_teacher_success(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)
    teacher = _make_teacher(institute_id=institute.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.invite_teacher = AsyncMock(return_value=teacher)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.post(
        "/teacher/invite",
        json={"name": "Ravi Kumar", "phone": "9123456780"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ravi Kumar"
    assert body["phone_number"] == "9123456780"
    assert body["institute_id"] == institute.id


async def test_invite_teacher_conflict_on_duplicate_phone(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.invite_teacher = AsyncMock(
        side_effect=ValueError("A teacher with this phone number already exists")
    )

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.post(
        "/teacher/invite",
        json={"name": "Ravi Kumar", "phone": "9123456780"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


async def test_invite_teacher_requires_auth(client):
    response = await client.post(
        "/teacher/invite",
        json={"name": "Ravi Kumar", "phone": "9123456780"},
    )
    # Missing Authorization header → 422 (field required) before 401
    assert response.status_code in (401, 422)


async def test_invite_teacher_no_institute_returns_404(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=None)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.post(
        "/teacher/invite",
        json={"name": "Ravi Kumar", "phone": "9123456780"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404


async def test_invite_teacher_invalid_phone_returns_422(client, override_supabase):
    """Body validation (phone pattern) should return 422.

    We mock auth to succeed so that the dependency doesn't short-circuit with 401
    before body validation is evaluated.
    """
    owner_teacher_id = uuid4()

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc

    response = await client.post(
        "/teacher/invite",
        json={"name": "Ravi Kumar", "phone": "1234"},
        headers={"Authorization": "Bearer sometoken"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /teacher/verify_otp
# ---------------------------------------------------------------------------


async def test_verify_otp_success(client):
    user_id = uuid4()

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.verify_otp = AsyncMock(
        return_value=("tok_abc_1234567890", "ref_xyz_1234567890", "authenticated", user_id)
    )

    from app import app

    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.post(
        "/teacher/verify_otp",
        json={"phone": "9123456780", "token": "123456"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["auth_token"] == "tok_abc_1234567890"
    assert body["refresh_token"] == "ref_xyz_1234567890"
    assert body["aud"] == "authenticated"
    assert body["user_id"] == str(user_id)


async def test_verify_otp_returns_401_on_failure(client):
    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.verify_otp = AsyncMock(side_effect=ValueError("OTP verification failed"))

    from app import app

    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.post(
        "/teacher/verify_otp",
        json={"phone": "9123456780", "token": "000000"},
    )

    assert response.status_code == 401
    assert "OTP verification failed" in response.json()["detail"]


async def test_verify_otp_no_pending_invite_returns_401(client):
    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.verify_otp = AsyncMock(
        side_effect=ValueError("No pending teacher invite found for this phone number")
    )

    from app import app

    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.post(
        "/teacher/verify_otp",
        json={"phone": "9123456780", "token": "654321"},
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /teacher/me
# ---------------------------------------------------------------------------


async def test_get_teacher_me_returns_profile(client):
    user_id = uuid4()
    teacher = _make_teacher(user_id=user_id)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=user_id)
    mock_teacher_svc.get_teacher_by_user_id = AsyncMock(return_value=teacher)

    from app import app

    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.get("/teacher/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Ravi Kumar"
    assert body["phone_number"] == "9123456780"


async def test_get_teacher_me_returns_404_when_not_found(client):
    user_id = uuid4()

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=user_id)
    mock_teacher_svc.get_teacher_by_user_id = AsyncMock(return_value=None)

    from app import app

    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.get("/teacher/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 404


async def test_get_teacher_me_returns_401_on_bad_token(client):
    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(
        side_effect=Exception("invalid token")
    )

    from app import app

    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.get("/teacher/me", headers={"Authorization": "Bearer badtoken"})

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /teacher/ (list teachers)
# ---------------------------------------------------------------------------


async def test_list_teachers_returns_list(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)
    t1 = _make_teacher(teacher_id=1, institute_id=institute.id)
    t2 = _make_teacher(teacher_id=2, institute_id=institute.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.get_teachers_by_institute = AsyncMock(return_value=[t1, t2])

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.get(
        "/teacher/", headers={"Authorization": "Bearer sometoken"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2


async def test_list_teachers_returns_empty_list(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.get_teachers_by_institute = AsyncMock(return_value=[])

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.get(
        "/teacher/", headers={"Authorization": "Bearer sometoken"}
    )

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# DELETE /teacher/{teacher_id}
# ---------------------------------------------------------------------------


async def test_remove_teacher_success(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.remove_teacher = AsyncMock(return_value=None)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.delete(
        "/teacher/1", headers={"Authorization": "Bearer sometoken"}
    )

    assert response.status_code == 204


async def test_remove_teacher_not_found_returns_404(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.remove_teacher = AsyncMock(side_effect=ValueError("Teacher not found"))

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.delete(
        "/teacher/99", headers={"Authorization": "Bearer sometoken"}
    )

    assert response.status_code == 404
    assert "Teacher not found" in response.json()["detail"]


async def test_remove_teacher_wrong_institute_returns_404(client, override_supabase):
    owner_teacher_id = uuid4()
    owner = _make_owner(teacher_id=owner_teacher_id)
    institute = _make_institute(owner_id=owner.id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    mock_teacher_svc = MagicMock(spec=TeacherService)
    mock_teacher_svc.get_current_teacher_user_id = AsyncMock(return_value=owner_teacher_id)
    mock_teacher_svc.remove_teacher = AsyncMock(
        side_effect=ValueError("Teacher does not belong to this institute")
    )

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_teacher_service] = lambda: mock_teacher_svc

    response = await client.delete(
        "/teacher/5", headers={"Authorization": "Bearer sometoken"}
    )

    assert response.status_code == 404
