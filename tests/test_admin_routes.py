"""
Tests for routes/admin_route.py — the manual payment-link backfill endpoint.

Auth here is a static secret header (X-Admin-Secret), not owner JWT — this
endpoint operates across institutes, not on behalf of one logged-in owner.
All service calls are mocked.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from models.institute_base import InstituteSchema
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service


async def test_backfill_requires_admin_secret_header(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = "s3cr3t"

        resp = await client.post("/admin/backfill-payment-links", json={})

    assert resp.status_code == 401


async def test_backfill_rejects_wrong_admin_secret(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = "s3cr3t"

        resp = await client.post(
            "/admin/backfill-payment-links",
            json={},
            headers={"X-Admin-Secret": "wrong"},
        )

    assert resp.status_code == 401


async def test_backfill_returns_503_when_not_configured(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = None

        resp = await client.post(
            "/admin/backfill-payment-links",
            json={},
            headers={"X-Admin-Secret": "anything"},
        )

    assert resp.status_code == 503


async def test_backfill_succeeds_with_correct_secret_and_returns_summary(client):
    from app import app

    fee_svc = MagicMock(spec=FeeService)
    fee_svc.backfill_missing_payment_links = AsyncMock(
        return_value={
            "month": date(2026, 6, 1),
            "checked": 3,
            "generated": 2,
            "skipped_no_razorpay": 1,
            "failed": 0,
            "errors": [],
        }
    )
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/backfill-payment-links",
                json={},
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 2
    _, kwargs = fee_svc.backfill_missing_payment_links.call_args
    assert kwargs["institute_id"] is None
    assert kwargs["month"] is None


async def test_backfill_passes_institute_id_from_request_body(client):
    from app import app

    fee_svc = MagicMock(spec=FeeService)
    fee_svc.backfill_missing_payment_links = AsyncMock(
        return_value={
            "month": date(2026, 6, 1),
            "checked": 0,
            "generated": 0,
            "skipped_no_razorpay": 0,
            "failed": 0,
            "errors": [],
        }
    )
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/backfill-payment-links",
                json={"institute_id": 42},
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    _, kwargs = fee_svc.backfill_missing_payment_links.call_args
    assert kwargs["institute_id"] == 42


async def test_generate_site_requires_admin_secret_header(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = "s3cr3t"

        resp = await client.post(
            "/admin/institute/1/generate-site",
            json={
                "slug": "test-slug",
                "address": "x",
                "phone_public": "9876543210",
                "email_public": "hi@example.com",
                "description": "x",
                "course_fee_display": "x",
            },
        )

    assert resp.status_code == 401


async def test_generate_site_succeeds_with_correct_secret(client):
    from app import app

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.generate_site = AsyncMock(
        return_value=InstituteSchema(
            id=1, owner_id=1, name="Test", city="Delhi", join_code="TEST0001",
            slug="test-slug", color_scheme="teal",
        )
    )
    app.dependency_overrides[get_institute_service] = lambda: institute_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/institute/1/generate-site",
                json={
                    "slug": "test-slug",
                    "address": "1 Test Road",
                    "phone_public": "9876543210",
                    "email_public": "hi@example.com",
                    "description": "Maths tuition",
                    "course_fee_display": "Rs 3000/month",
                },
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["public_url"] == "https://test-slug.batchbook.in"


async def test_generate_site_returns_400_on_value_error(client):
    from app import app

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.generate_site = AsyncMock(side_effect=ValueError("slug already taken"))
    app.dependency_overrides[get_institute_service] = lambda: institute_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/institute/1/generate-site",
                json={
                    "slug": "taken",
                    "address": "x",
                    "phone_public": "9876543210",
                    "email_public": "hi@example.com",
                    "description": "x",
                    "course_fee_display": "x",
                },
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400


async def test_generate_site_returns_404_on_no_institute_found(client):
    from app import app

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.generate_site = AsyncMock(
        side_effect=ValueError("No institute found with id 999")
    )
    app.dependency_overrides[get_institute_service] = lambda: institute_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/institute/999/generate-site",
                json={
                    "slug": "test-slug",
                    "address": "x",
                    "phone_public": "9876543210",
                    "email_public": "hi@example.com",
                    "description": "x",
                    "course_fee_display": "x",
                },
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
