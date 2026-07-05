"""
Tests for services/institute_service.py — InstituteService.

Symbols under test:
  Class:services/institute_service.py:InstituteService
    create_institute, get_institute_by_owner_id, update_institute
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.institute_base import InstituteSchema, RazorpayStatus
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

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)),
        patch.object(service.institute_repo, "create", new=create_mock),
    ):
        result = await service.create_institute(mock_db, owner_id=5, name="Sharma Classes", city="Gurugram")

    assert result is expected
    create_mock.assert_called_once()


async def test_create_institute_builds_correct_schema(service, mock_db):
    captured = {}

    async def capture_create(db, institute):
        captured["institute"] = institute
        return institute

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)),
        patch.object(service.institute_repo, "create", new=AsyncMock(side_effect=capture_create)),
    ):
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


# --- get_by_id ---


async def test_get_by_id_returns_institute(service, mock_db):
    expected = _make_institute(owner_id=3)
    expected.id = 10

    with patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=expected)):
        result = await service.get_by_id(mock_db, institute_id=10)

    assert result is expected


async def test_get_by_id_returns_none_when_missing(service, mock_db):
    with patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=None)):
        result = await service.get_by_id(mock_db, institute_id=999)

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


# --- connect_razorpay ---

async def test_connect_razorpay_encrypts_and_updates(service, mock_db):
    existing = _make_institute(owner_id=4)
    updated = _make_institute(owner_id=4)
    updated.razorpay_key_id = "rzp_live_abc123"
    updated.razorpay_status = RazorpayStatus.CONNECTED
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.return_value = {"items": []}
        result = await service.connect_razorpay(
            mock_db, owner_id=4, key_id="rzp_live_abc123", key_secret="supersecretvalue"
        )

    assert result is updated
    mock_client_cls.assert_called_once_with(auth=("rzp_live_abc123", "supersecretvalue"))
    mock_client_cls.return_value.payment.all.assert_called_once_with({"count": 1})
    update_mock.assert_called_once()
    call_args = update_mock.call_args[0]
    assert call_args[1] is existing
    updates = call_args[2]
    assert updates["razorpay_key_id"] == "rzp_live_abc123"
    assert updates["razorpay_status"] == RazorpayStatus.CONNECTED
    # secret must never be stored in plaintext
    assert updates["razorpay_key_secret_encrypted"] != "supersecretvalue"


async def test_connect_razorpay_raises_when_no_institute(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="No institute found"):
            await service.connect_razorpay(
                mock_db, owner_id=999, key_id="rzp_live_x", key_secret="secretvalue"
            )


async def test_connect_razorpay_rejects_test_mode_key(service, mock_db):
    from services.institute_service import InvalidRazorpayCredentialsError

    existing = _make_institute(owner_id=4)
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        with pytest.raises(InvalidRazorpayCredentialsError, match="Test-mode keys"):
            await service.connect_razorpay(
                mock_db, owner_id=4, key_id="rzp_test_abc123", key_secret="supersecretvalue"
            )

    # never reached the live check or persisted anything
    mock_client_cls.assert_not_called()
    update_mock.assert_not_called()


async def test_connect_razorpay_raises_when_credentials_fail_live_check(service, mock_db):
    import razorpay

    from services.institute_service import InvalidRazorpayCredentialsError

    existing = _make_institute(owner_id=4)
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.side_effect = razorpay.errors.BadRequestError(
            "Authentication failed"
        )
        with pytest.raises(InvalidRazorpayCredentialsError, match="Razorpay rejected these credentials"):
            await service.connect_razorpay(
                mock_db, owner_id=4, key_id="rzp_live_bad", key_secret="wrongsecret"
            )

    # invalid credentials must never be persisted
    update_mock.assert_not_called()


# --- set_webhook_secret ---


async def test_set_webhook_secret_encrypts_and_updates(service, mock_db):
    existing = _make_institute(owner_id=4)
    updated = _make_institute(owner_id=4)
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.set_webhook_secret(
            mock_db, owner_id=4, webhook_secret="whsec_supersecretvalue"
        )

    assert result is updated
    update_mock.assert_called_once()
    call_args = update_mock.call_args[0]
    assert call_args[1] is existing
    updates = call_args[2]
    assert list(updates.keys()) == ["razorpay_webhook_secret_encrypted"]
    # secret must never be stored in plaintext
    assert updates["razorpay_webhook_secret_encrypted"] != "whsec_supersecretvalue"


async def test_set_webhook_secret_raises_when_no_institute(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="No institute found"):
            await service.set_webhook_secret(
                mock_db, owner_id=999, webhook_secret="whsec_x"
            )


# --- flag_needs_reconnect ---


async def test_flag_needs_reconnect_updates_status(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.CONNECTED
    updated = _make_institute(owner_id=4)
    updated.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.flag_needs_reconnect(mock_db, institute_id=10)

    assert result is updated
    update_mock.assert_called_once_with(
        mock_db, existing, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
    )


async def test_flag_needs_reconnect_is_noop_when_already_flagged(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.flag_needs_reconnect(mock_db, institute_id=10)

    assert result is existing
    update_mock.assert_not_called()


async def test_flag_needs_reconnect_returns_none_when_institute_missing(service, mock_db):
    with patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=None)):
        result = await service.flag_needs_reconnect(mock_db, institute_id=999)

    assert result is None


# --- test_razorpay_connection ---


async def test_test_connection_flips_needs_reconnect_to_connected_on_success(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    existing.razorpay_key_id = "rzp_live_abc123"
    existing.razorpay_key_secret_encrypted = "encrypted-blob"
    updated = _make_institute(owner_id=4)
    updated.razorpay_status = RazorpayStatus.CONNECTED
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.decrypt_secret", return_value="plainsecret"),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.return_value = {"items": []}
        result = await service.test_razorpay_connection(mock_db, owner_id=4)

    assert result is updated
    mock_client_cls.assert_called_once_with(auth=("rzp_live_abc123", "plainsecret"))
    update_mock.assert_called_once_with(
        mock_db, existing, {"razorpay_status": RazorpayStatus.CONNECTED}
    )


async def test_test_connection_noop_when_already_connected_and_still_valid(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.CONNECTED
    existing.razorpay_key_id = "rzp_live_abc123"
    existing.razorpay_key_secret_encrypted = "encrypted-blob"
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.decrypt_secret", return_value="plainsecret"),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.return_value = {"items": []}
        result = await service.test_razorpay_connection(mock_db, owner_id=4)

    assert result is existing
    update_mock.assert_not_called()


async def test_test_connection_flips_connected_to_needs_reconnect_on_auth_failure(service, mock_db):
    import razorpay

    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.CONNECTED
    existing.razorpay_key_id = "rzp_live_abc123"
    existing.razorpay_key_secret_encrypted = "encrypted-blob"
    updated = _make_institute(owner_id=4)
    updated.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.decrypt_secret", return_value="plainsecret"),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.side_effect = razorpay.errors.BadRequestError(
            "Authentication failed"
        )
        result = await service.test_razorpay_connection(mock_db, owner_id=4)

    assert result is updated
    update_mock.assert_called_once_with(
        mock_db, existing, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
    )


async def test_test_connection_raises_when_no_institute(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="No institute found"):
            await service.test_razorpay_connection(mock_db, owner_id=999)


async def test_test_connection_raises_when_no_credentials_saved(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.razorpay_key_id = None
    existing.razorpay_key_secret_encrypted = None

    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)):
        with pytest.raises(ValueError, match="No Razorpay credentials saved"):
            await service.test_razorpay_connection(mock_db, owner_id=4
            )
