"""
Tests for routes/public_route.py — the unauthenticated public institute endpoint
used by the Tier 2 site generator (Task F.8).
"""

from unittest.mock import AsyncMock, MagicMock

from models.institute_base import InstituteSchema, RazorpayStatus
from services.institute_service import InstituteService, get_institute_service


def _fake_institute(**overrides) -> InstituteSchema:
    defaults = dict(
        id=1,
        owner_id=1,
        name="Test Institute",
        city="Delhi",
        join_code="TEST0001",
        razorpay_key_id="rzp_live_should_not_leak",
        razorpay_status=RazorpayStatus.CONNECTED,
        slug="test-institute",
        address="1 Test Road",
        phone_public="9876543210",
        email_public="hi@example.com",
        description="Maths tuition",
        course_fee_display="Rs 3000/month",
        color_scheme="teal",
    )
    defaults.update(overrides)
    return InstituteSchema(**defaults)


async def test_get_public_institute_returns_200_with_allowed_fields(client):
    from app import app

    svc = MagicMock(spec=InstituteService)
    svc.get_public_by_slug = AsyncMock(return_value=_fake_institute())
    app.dependency_overrides[get_institute_service] = lambda: svc

    try:
        resp = await client.get("/public/institute/test-institute")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Institute"
    assert data["color_scheme"] == "teal"
    assert "owner_id" not in data
    assert "join_code" not in data
    assert "razorpay_key_id" not in data
    assert "razorpay_status" not in data


async def test_get_public_institute_returns_404_for_unknown_slug(client):
    from app import app

    svc = MagicMock(spec=InstituteService)
    svc.get_public_by_slug = AsyncMock(return_value=None)
    app.dependency_overrides[get_institute_service] = lambda: svc

    try:
        resp = await client.get("/public/institute/does-not-exist")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
