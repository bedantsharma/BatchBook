"""Unit tests for clients/razorpay_client.py."""

import pytest
from unittest.mock import patch, MagicMock

import clients.razorpay_client as rp_module


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
