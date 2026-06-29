"""WhatsApp notifications via Meta Cloud API.

All four functions are fire-and-forget: they catch and log errors rather than
raising, so a transient WhatsApp API failure never breaks the caller's HTTP
response.

Phone number format: parent_phone must be the 10-digit Indian mobile number
(e.g. "9876543210"). The country code 91 is prepended automatically.
"""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from clients.whatsapp_client import send_template_message
from models.notification_base import (
    NotificationSchema,
    NotificationStatus,
    NotificationType,
)
from repositories.notification_repository import NotificationRepository

_REMINDER_TYPES = {NotificationType.FEE_REMINDER, NotificationType.ABSENCE}


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
        logger.info(
            "[WhatsApp] sent template={template} phone=****{phone_suffix} student={student}",
            template="enrollment_invite",
            phone_suffix=parent_phone[-4:],
            student=student_name,
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

    TODO: switch to a URL button CTA once Razorpay short_url format is confirmed
    consistent (base URL would be https://rzp.io/l/ with the unique suffix as the
    dynamic parameter). A button is more prominent and always tappable on Android.
    Requires recreating the template in WhatsApp Manager with a button component.
    """
    link_text = payment_link or "Contact your institute"
    amount_str = f"{int(amount):,}" if amount == int(amount) else f"{float(amount):.2f}"
    try:
        await send_template_message(
            to=_to(parent_phone),
            template_name="fee_reminder",
            components=_body(student_name, amount_str, batch_name, due_date, link_text),
        )
        logger.info(
            "[WhatsApp] sent template={template} phone=****{phone_suffix} student={student}",
            template="fee_reminder",
            phone_suffix=parent_phone[-4:],
            student=student_name,
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
        logger.info(
            "[WhatsApp] sent template={template} phone=****{phone_suffix} student={student}",
            template="fee_receipt",
            phone_suffix=parent_phone[-4:],
            student=student_name,
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
        logger.info(
            "[WhatsApp] sent template={template} phone=****{phone_suffix} student={student}",
            template="absence_alert",
            phone_suffix=parent_phone[-4:],
            student=student_name,
        )
    except Exception as exc:
        logger.error(
            f"[WhatsApp] absence_alert failed for +91{parent_phone} "
            f"student={student_name!r} date={date}: {exc}"
        )


async def dispatch_in_background(**kwargs) -> None:
    """Background-task wrapper: opens its own DB session and dispatches.

    Pass the same keyword args as ``dispatch`` minus ``db``.
    """
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await dispatch(db, **kwargs)
        except Exception as exc:  # never let a background failure escape
            logger.error(f"[WhatsApp] background dispatch failed: {exc}")


async def dispatch(
    db: AsyncSession,
    *,
    parent,
    student_id: int | None,
    institute_id: int | None,
    type: NotificationType,
    template_name: str,
    components: list[dict],
    join_url: str | None = None,
    force: bool = False,
) -> NotificationSchema:
    """Send a WhatsApp template (verification-gated) and audit the result.

    - Verified parent (``parent.user_id`` set) or non-reminder type → send ``template_name``.
    - Unverified parent + reminder type → send ``enrollment_invite`` link instead and log
      status ``skipped_unverified``.
    - Every outcome (sent / skipped / failed) is persisted to the Notification table with the
      message components, institute_id, and the raw WhatsApp API response in ``meta_data``.
    """
    repo = NotificationRepository()
    verified = parent is not None and parent.user_id is not None
    is_reminder = type in _REMINDER_TYPES

    if not verified and is_reminder and not force:
        if join_url is None:
            # Cannot build a valid enrollment_invite without a link. Sending the original
            # reminder components under the enrollment_invite template would cause a
            # guaranteed Meta API param-mismatch (3-param template vs 5-param body).
            # Skip the send entirely and record the reason.
            notification = NotificationSchema(
                parent_id=getattr(parent, "id", None),
                student_id=student_id,
                institute_id=institute_id,
                type=type,
                status=NotificationStatus.SKIPPED_UNVERIFIED,
                reason="parent number not verified; no invite link available",
                meta_data={
                    "message": {"template": template_name, "components": components},
                    "institute_id": institute_id,
                    "whatsapp_response": None,
                },
            )
            return await repo.create(db, notification)
        # Re-invite instead of reminding (join_url is available)
        sent_template = "enrollment_invite"
        sent_components = _body("Student", "your institute", join_url)
        status = NotificationStatus.SKIPPED_UNVERIFIED
        reason = "parent number not verified"
    else:
        status = NotificationStatus.SENT
        reason = None
        sent_template = template_name
        sent_components = components

    whatsapp_response = None
    try:
        whatsapp_response = await send_template_message(
            to=_to(parent.phone_number),
            template_name=sent_template,
            components=sent_components,
        )
    except Exception as exc:
        status = NotificationStatus.FAILED
        reason = str(exc)
        logger.error(f"[WhatsApp] dispatch {sent_template} failed: {exc}")

    notification = NotificationSchema(
        parent_id=getattr(parent, "id", None),
        student_id=student_id,
        institute_id=institute_id,
        type=type,
        status=status,
        reason=reason,
        meta_data={
            "message": {"template": sent_template, "components": sent_components},
            "institute_id": institute_id,
            "whatsapp_response": whatsapp_response,
        },
    )
    return await repo.create(db, notification)
