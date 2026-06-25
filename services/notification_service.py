"""WhatsApp notifications via Meta Cloud API.

All four functions are fire-and-forget: they catch and log errors rather than
raising, so a transient WhatsApp API failure never breaks the caller's HTTP
response.

Phone number format: parent_phone must be the 10-digit Indian mobile number
(e.g. "9876543210"). The country code 91 is prepended automatically.
"""

from loguru import logger

from clients.whatsapp_client import send_template_message


def _to(parent_phone: str) -> str:
    """Return the E.164-style number without '+' as required by Meta Cloud API."""
    return f"91{parent_phone}"


def _body(*texts: str) -> list[dict]:
    """Build a single body component with positional text parameters."""
    return [
        {
            "type": "body",
            "parameters": [{"type": "text", "text": t} for t in texts],
        }
    ]


async def send_enrollment_invite(
    parent_phone: str,
    student_name: str,
    institute_name: str,
    join_url: str,
) -> None:
    """Template enrollment_invite:
    'Hi! {{1}} has been added to {{2}} on BatchBook.
     Click to view attendance, fees & schedule: {{3}}
     Thank you BatchBook AI'
    """
    try:
        await send_template_message(
            to=_to(parent_phone),
            template_name="enrollment_invite",
            components=_body(student_name, institute_name, join_url),
        )
    except Exception as exc:
        logger.error(
            f"[WhatsApp] enrollment_invite failed for +91{parent_phone} "
            f"student={student_name!r}: {exc}"
        )


async def send_fee_reminder(
    parent_phone: str,
    student_name: str,
    amount: float,
    batch_name: str,
    due_date: str,
    payment_link: str | None,
) -> None:
    """Template fee_reminder:
    'Hi {{1}}, your fee of ₹{{2}} for {{3}} is due on {{4}}.
     Pay here: {{5}} Thank you Batchbook Ai'
    """
    link_text = payment_link or "Contact your institute"
    amount_str = f"{int(amount):,}" if amount == int(amount) else f"{float(amount):.2f}"
    try:
        await send_template_message(
            to=_to(parent_phone),
            template_name="fee_reminder",
            components=_body(student_name, amount_str, batch_name, due_date, link_text),
        )
    except Exception as exc:
        logger.error(
            f"[WhatsApp] fee_reminder failed for +91{parent_phone} "
            f"student={student_name!r} amount={amount}: {exc}"
        )


async def send_fee_receipt(
    parent_phone: str,
    student_name: str,
    amount: float,
    batch_name: str,
    paid_on: str,
) -> None:
    """Template fee_receipt:
    'Hi {{1}}, payment of ₹{{2}} received for {{3}} on {{4}}. Thank you!'
    """
    amount_str = f"{int(amount):,}" if amount == int(amount) else f"{float(amount):.2f}"
    try:
        await send_template_message(
            to=_to(parent_phone),
            template_name="fee_receipt",
            components=_body(student_name, amount_str, batch_name, paid_on),
        )
    except Exception as exc:
        logger.error(
            f"[WhatsApp] fee_receipt failed for +91{parent_phone} "
            f"student={student_name!r} amount={amount}: {exc}"
        )


async def send_absence_alert(
    parent_phone: str,
    student_name: str,
    batch_name: str,
    date: str,
) -> None:
    """Template absence_alert:
    'Hi, {{1}} was absent from {{2}} today ({{3}}).
     Please contact us if this is unexpected.'
    """
    try:
        await send_template_message(
            to=_to(parent_phone),
            template_name="absence_alert",
            components=_body(student_name, batch_name, date),
        )
    except Exception as exc:
        logger.error(
            f"[WhatsApp] absence_alert failed for +91{parent_phone} "
            f"student={student_name!r} date={date}: {exc}"
        )
