"""Live smoke test for the enrollment_invite WhatsApp template.

Reads META_WHATSAPP_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID from .env.
The recipient is hardcoded to 919352522722 for this debug run.

    uv run pytest tests/test_enrollment_invite_live.py -v -s

If you get 401: your token is expired. Grab a fresh one from
Meta for Developers → your app → WhatsApp → API Setup → Temporary access token
(or generate a permanent system-user token from Business Settings).
"""

import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

RECIPIENT = "919352522722"

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("META_WHATSAPP_TOKEN")
        and os.environ.get("META_WHATSAPP_PHONE_NUMBER_ID")
    ),
    reason="requires META_WHATSAPP_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID in .env",
)


async def test_enrollment_invite_send():
    """Send enrollment_invite template to 9352522722 and print full API response."""
    token = os.environ["META_WHATSAPP_TOKEN"]
    phone_number_id = os.environ["META_WHATSAPP_PHONE_NUMBER_ID"]

    url = f"https://graph.facebook.com/v23.0/{phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": RECIPIENT,
        "type": "template",
        "template": {
            "name": "enrollment_invite",
            "language": {"code": "en"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Bedant Sharma"},
                        {"type": "text", "text": "Sharma Classes"},
                        {"type": "text", "text": "https://batchbook.in/join/TEST123"},
                    ],
                }
            ],
        },
    }

    print(f"\nPOST {url}")
    print(f"Token prefix: {token[:12]}...")
    print(f"Phone number ID: {phone_number_id}")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=15.0,
        )

    print(f"\nHTTP status: {response.status_code}")
    print(f"Response body: {response.text}")

    if response.status_code == 401:
        body = response.json()
        error = body.get("error", {})
        print(f"\n--- 401 Diagnosis ---")
        print(f"Error code:    {error.get('code')}")
        print(f"Error type:    {error.get('type')}")
        print(f"Error message: {error.get('message')}")
        print(f"FbTrace ID:    {error.get('fbtrace_id')}")
        print(
            "\nFix: your META_WHATSAPP_TOKEN is expired or invalid.\n"
            "Go to Meta for Developers → your app → WhatsApp → API Setup\n"
            "and copy a fresh Temporary access token (valid 24h), or create\n"
            "a permanent System User token in Business Settings."
        )
        pytest.fail(f"401 Unauthorized — token is invalid/expired. Error: {error.get('message')}")

    response.raise_for_status()
    result = response.json()
    assert "messages" in result, f"Unexpected response: {result}"
    assert result["messages"][0]["id"].startswith("wamid."), f"Bad message ID: {result}"
    print(f"\nSuccess! Message ID: {result['messages'][0]['id']}")
