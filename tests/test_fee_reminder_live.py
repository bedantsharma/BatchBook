"""Live smoke test: generate a real Razorpay test-mode payment link, then send
it via the fee_reminder WhatsApp template to a real phone number.

Reads RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET and META_WHATSAPP_TOKEN/
META_WHATSAPP_PHONE_NUMBER_ID from .env. RAZORPAY_KEY_ID must be a test-mode
key (rzp_test_...) — the test refuses to run against anything else, since it
creates a real (but test-mode, no real money moves) Razorpay payment link and
sends a real WhatsApp message.

The recipient is hardcoded to 9352522722, same as
tests/test_enrollment_invite_live.py.

    uv run pytest tests/test_fee_reminder_live.py -v -s

If the WhatsApp call 404s/400s with a template-not-found or not-approved
error: fee_reminder may not be APPROVED on the WABA yet — check WhatsApp
Manager (see tests/test_whatsapp_live.py's note that only absence_alert was
approved as of an earlier check).

To test the payment link in a browser: open the printed short_url, pick UPI
at checkout, and use Razorpay's test UPI flow (no real bank/UPI app needed —
test mode simulates success/failure).
"""

import asyncio
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

RECIPIENT = "9352522722"  # 10-digit; the fee_reminder template call prepends "91"

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("RAZORPAY_KEY_ID")
        and os.environ.get("RAZORPAY_KEY_SECRET")
        and os.environ.get("META_WHATSAPP_TOKEN")
        and os.environ.get("META_WHATSAPP_PHONE_NUMBER_ID")
    ),
    reason="requires RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, META_WHATSAPP_TOKEN, "
    "META_WHATSAPP_PHONE_NUMBER_ID in .env",
)


async def test_generate_payment_link_and_send_fee_reminder():
    """End-to-end: create a real test-mode Razorpay payment link, then send it
    via the fee_reminder WhatsApp template and assert on the real API response."""
    from clients.razorpay_client import get_razorpay_client
    from clients.whatsapp_client import send_template_message

    key_id = os.environ["RAZORPAY_KEY_ID"]
    assert key_id.startswith("rzp_test_"), (
        f"RAZORPAY_KEY_ID={key_id[:12]}... is not a test-mode key (rzp_test_...) — "
        "refusing to run this smoke test against what looks like a live key."
    )

    razorpay_client = get_razorpay_client()
    link_data = {
        "amount": 50000,  # ₹500.00 in paise
        "currency": "INR",
        "accept_partial": False,
        "description": "BatchBook test fee reminder",
        "reminder_enable": False,
    }
    link_result = await asyncio.to_thread(razorpay_client.payment_link.create, link_data)
    payment_link = link_result["short_url"]
    print(f"\nRazorpay test-mode payment link: {payment_link}")
    assert payment_link.startswith("https://"), f"Unexpected payment link: {link_result}"

    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "Test Student"},
                {"type": "text", "text": "500"},
                {"type": "text", "text": "Maths 10th"},
                {"type": "text", "text": "5 Jul 2026"},
                {"type": "text", "text": payment_link},
            ],
        }
    ]

    whatsapp_result = await send_template_message(
        to=f"91{RECIPIENT}",
        template_name="fee_reminder",
        components=components,
    )
    print(f"\nMeta API response: {whatsapp_result}")
    assert "messages" in whatsapp_result, f"Unexpected response: {whatsapp_result}"
    assert whatsapp_result["messages"][0]["id"].startswith("wamid."), (
        f"Bad message ID: {whatsapp_result}"
    )
    print(f"\nSuccess! fee_reminder sent to +91{RECIPIENT} with link {payment_link}")
