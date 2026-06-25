"""Live smoke test against the real Meta WhatsApp Cloud API.

Not part of the regular test suite — skipped unless real credentials and a
target phone number are present. Reads META_WHATSAPP_TOKEN and
META_WHATSAPP_PHONE_NUMBER_ID from .env (same as the app), so no need to pass
them on the command line. Only the recipient number needs to be set:

    META_WHATSAPP_TEST_RECIPIENT=91XXXXXXXXXX \\
    uv run pytest tests/test_whatsapp_live.py -v -s

Uses BatchBook's own `absence_alert` template, since it's the only one
APPROVED on the WABA at the time of writing (fee_reminder, fee_receipt,
enrollment_invite were still PENDING review). Swap the template name here
once another one gets approved.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("META_WHATSAPP_TOKEN")
        and os.environ.get("META_WHATSAPP_PHONE_NUMBER_ID")
        and os.environ.get("META_WHATSAPP_TEST_RECIPIENT")
    ),
    reason="requires META_WHATSAPP_TOKEN, META_WHATSAPP_PHONE_NUMBER_ID, "
    "META_WHATSAPP_TEST_RECIPIENT env vars",
)


async def test_can_send_absence_alert_template():
    from clients.whatsapp_client import send_template_message

    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Rahul"},
                {"type": "text", "text": "MTH 101"},
                {"type": "text", "text": "27 May 2026"},
            ],
        }
    ]

    result = await send_template_message(
        to=os.environ["META_WHATSAPP_TEST_RECIPIENT"],
        template_name="absence_alert",
        language="en",
        components=components,
    )

    print(f"\nMeta API response: {result}")
    assert "messages" in result
    assert result["messages"][0]["id"].startswith("wamid.")
