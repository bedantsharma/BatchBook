"""Unit tests for clients/razorpay_client.py."""

from unittest.mock import patch

import pytest

import clients.razorpay_client as rp_module
from models.institute_base import InstituteSchema, RazorpayStatus


def _reset():
    rp_module._client = None


def test_get_razorpay_client_creates_client_with_credentials():
    _reset()
    with patch("clients.razorpay_client.razorpay.Client") as mock_cls:
        with patch("clients.razorpay_client.get_settings") as mock_settings:
            mock_settings.return_value.razorpay_key_id = "rzp_test_abc"
            mock_settings.return_value.razorpay_key_secret = "secret_xyz"

            from clients.razorpay_client import get_razorpay_client
            get_razorpay_client()

            mock_cls.assert_called_once_with(auth=("rzp_test_abc", "secret_xyz"))


def test_get_razorpay_client_returns_singleton():
    _reset()
    with patch("clients.razorpay_client.razorpay.Client") as mock_cls:
        with patch("clients.razorpay_client.get_settings") as mock_settings:
            mock_settings.return_value.razorpay_key_id = "rzp_test_abc"
            mock_settings.return_value.razorpay_key_secret = "secret_xyz"

            from clients.razorpay_client import get_razorpay_client
            c1 = get_razorpay_client()
            c2 = get_razorpay_client()

            assert c1 is c2
            mock_cls.assert_called_once()


def test_get_razorpay_client_raises_without_credentials():
    _reset()
    with patch("clients.razorpay_client.get_settings") as mock_settings:
        mock_settings.return_value.razorpay_key_id = None
        mock_settings.return_value.razorpay_key_secret = None

        from clients.razorpay_client import get_razorpay_client
        with pytest.raises(RuntimeError, match="Razorpay credentials not configured"):
            get_razorpay_client()


def _make_institute(status=RazorpayStatus.CONNECTED, key_id="rzp_live_abc", secret_encrypted="enc-blob"):
    from unittest.mock import MagicMock

    inst = MagicMock(spec=InstituteSchema)
    inst.razorpay_status = status
    inst.razorpay_key_id = key_id
    inst.razorpay_key_secret_encrypted = secret_encrypted
    return inst


def test_build_institute_razorpay_client_returns_none_when_not_connected():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(status=RazorpayStatus.NOT_CONNECTED)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_returns_none_when_needs_reconnect():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(status=RazorpayStatus.NEEDS_RECONNECT)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_returns_none_when_missing_key_id():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(key_id=None)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_returns_none_when_missing_secret():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(secret_encrypted=None)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_builds_client_when_connected():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute()
    with patch("clients.razorpay_client.decrypt_secret", return_value="plain-secret") as mock_decrypt:
        with patch("clients.razorpay_client.razorpay.Client") as mock_cls:
            build_institute_razorpay_client(institute)

            mock_decrypt.assert_called_once_with("enc-blob")
            mock_cls.assert_called_once_with(auth=("rzp_live_abc", "plain-secret"))
