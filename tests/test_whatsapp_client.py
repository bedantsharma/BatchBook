"""Unit tests for clients/whatsapp_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


async def test_send_template_message_raises_without_credentials():
    with patch("clients.whatsapp_client.get_settings") as mock_settings:
        mock_settings.return_value.meta_whatsapp_token = None
        mock_settings.return_value.meta_whatsapp_phone_number_id = None

        from clients.whatsapp_client import send_template_message

        with pytest.raises(RuntimeError, match="Meta WhatsApp credentials not configured"):
            await send_template_message("919876543210", "fee_reminder")


async def test_send_template_message_posts_correct_request():
    with (
        patch("clients.whatsapp_client.get_settings") as mock_settings,
        patch("clients.whatsapp_client.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.return_value.meta_whatsapp_token = "token123"
        mock_settings.return_value.meta_whatsapp_phone_number_id = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        from clients.whatsapp_client import send_template_message

        result = await send_template_message("919876543210", "fee_reminder", language="en")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "https://graph.facebook.com/v23.0/1234567890/messages"
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer token123"
        assert call_args.kwargs["json"] == {
            "messaging_product": "whatsapp",
            "to": "919876543210",
            "type": "template",
            "template": {"name": "fee_reminder", "language": {"code": "en"}},
        }
        assert result == {"messages": [{"id": "wamid.abc"}]}


async def test_send_template_message_includes_components_when_given():
    with (
        patch("clients.whatsapp_client.get_settings") as mock_settings,
        patch("clients.whatsapp_client.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.return_value.meta_whatsapp_token = "token123"
        mock_settings.return_value.meta_whatsapp_phone_number_id = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        from clients.whatsapp_client import send_template_message

        components = [{"type": "body", "parameters": [{"type": "text", "text": "Asha"}]}]
        await send_template_message("919876543210", "fee_reminder", components=components)

        sent_payload = mock_client.post.call_args.kwargs["json"]
        assert sent_payload["template"]["components"] == components


async def test_send_template_message_raises_on_http_error():
    with (
        patch("clients.whatsapp_client.get_settings") as mock_settings,
        patch("clients.whatsapp_client.httpx.AsyncClient") as mock_client_cls,
    ):
        mock_settings.return_value.meta_whatsapp_token = "token123"
        mock_settings.return_value.meta_whatsapp_phone_number_id = "1234567890"

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=MagicMock(status_code=400)
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        from clients.whatsapp_client import send_template_message

        with pytest.raises(httpx.HTTPStatusError):
            await send_template_message("919876543210", "fee_reminder")
