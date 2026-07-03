from decimal import Decimal
from typing import Annotated

import razorpay
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from models.fee_record_base import FeeStatus
from services.crypto_service import EncryptionNotConfigured, decrypt_secret
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service

router = APIRouter(prefix="/webhooks")

FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


@router.post(
    "/razorpay/{institute_id}",
    summary="Razorpay webhook — auto-confirms fee payments for one institute",
)
async def razorpay_webhook(
    institute_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    fee_service: FeeServiceDep,
    institute_service: InstituteServiceDep,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    """No JWT auth — each institute's own Razorpay account signs its calls with a
    secret only that institute knows (set via `PATCH /owner/institute/payouts/webhook`),
    so the signature itself is the authentication.

    Only handles the `payment_link.paid` event today. Everything else is
    acknowledged with 200 so Razorpay doesn't retry, but otherwise ignored.
    """
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")

    raw_body = await request.body()

    institute = await institute_service.get_by_id(db, institute_id)
    if not institute or not institute.razorpay_webhook_secret_encrypted:
        raise HTTPException(status_code=404, detail="Webhook not configured for this institute")

    try:
        secret = decrypt_secret(institute.razorpay_webhook_secret_encrypted)
    except EncryptionNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        razorpay.Utility().verify_webhook_signature(
            raw_body.decode("utf-8"), x_razorpay_signature, secret
        )
    except razorpay.errors.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from e

    payload = await request.json()
    if payload.get("event") != "payment_link.paid":
        return {"status": "ignored", "event": payload.get("event")}

    plink_entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})

    short_url = plink_entity.get("short_url")
    amount_paid_paise = plink_entity.get("amount_paid")
    payment_id = payment_entity.get("id")

    if not short_url or amount_paid_paise is None:
        raise HTTPException(status_code=400, detail="Malformed payment_link.paid payload")

    record = await fee_service.get_record_by_payment_link(db, short_url)
    if not record:
        logger.warning(f"payment_link.paid webhook: no FeeRecord found for link {short_url}")
        return {"status": "ignored", "reason": "no matching fee record"}

    if record.status == FeeStatus.FULLY_PAID:
        # Already applied — Razorpay retried a webhook we've already handled.
        return {"status": "ok", "note": "already fully paid"}

    new_total = record.amount_paid + Decimal(amount_paid_paise) / 100

    try:
        updated = await fee_service.mark_payment(
            db=db, record_id=record.id, amount_paid=new_total, reference=payment_id
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    await fee_service.notify_fee_receipt_if_fully_paid(db, background_tasks, updated)

    return {"status": "ok"}
