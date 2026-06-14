# TODO: Wire WATI credentials before enabling notifications.
# Required env vars: WATI_API_ENDPOINT, WATI_API_TOKEN
# Steps:
#   1. Add WATI_API_ENDPOINT and WATI_API_TOKEN to config.py Settings class
#   2. Create clients/wati_client.py with an async httpx client
#   3. Replace the stub bodies below with real wati_client calls
#   4. Create WhatsApp templates in WATI dashboard (see BATCHBOOK_ROADMAP_V2.md Phase D)
#
# Until then, all functions log intent and return None silently.
# The invite join URL is sent as a fallback instruction to the caller.

from loguru import logger


async def send_enrollment_invite(
    parent_phone: str,
    student_name: str,
    institute_name: str,
    join_url: str,
) -> None:
    """Notify parent they have been enrolled by an institute owner.

    Template (pending): "Hi! {{student_name}} has been added to {{institute_name}} on BatchBook.
    Click to view attendance, fees & schedule: {{join_url}}"
    """
    logger.info(
        f"[WATI stub] Would send enrollment invite to +91{parent_phone} "
        f"for student={student_name!r} institute={institute_name!r} url={join_url}"
    )


async def send_fee_reminder(
    parent_phone: str,
    student_name: str,
    amount: float,
    batch_name: str,
    due_date: str,
    payment_link: str | None,
) -> None:
    """Template (pending): fee_reminder — due amount + payment link."""
    logger.info(
        f"[WATI stub] Would send fee reminder to +91{parent_phone} "
        f"student={student_name!r} amount=₹{amount} batch={batch_name!r}"
    )


async def send_fee_receipt(
    parent_phone: str,
    student_name: str,
    amount: float,
    batch_name: str,
    paid_on: str,
) -> None:
    """Template (pending): fee_receipt — payment confirmation."""
    logger.info(
        f"[WATI stub] Would send fee receipt to +91{parent_phone} "
        f"student={student_name!r} amount=₹{amount}"
    )


async def send_absence_alert(
    parent_phone: str,
    student_name: str,
    batch_name: str,
    date: str,
) -> None:
    """Template (pending): absence_alert — student was marked absent."""
    logger.info(
        f"[WATI stub] Would send absence alert to +91{parent_phone} "
        f"student={student_name!r} batch={batch_name!r} date={date}"
    )
