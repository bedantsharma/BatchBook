import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.session import get_db
from routes.requests.backfill_payment_links_request import BackfillPaymentLinksRequest
from routes.responses.backfill_payment_links_response import BackfillPaymentLinksResponse
from services.fee_service import FeeService, get_fee_service

router = APIRouter(prefix="/admin")

FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]


async def _verify_admin_secret(x_admin_secret: Annotated[str | None, Header()] = None) -> None:
    settings = get_settings()
    if not settings.admin_backfill_secret:
        raise HTTPException(
            status_code=503,
            detail="Admin backfill endpoint not configured — set ADMIN_BACKFILL_SECRET in .env",
        )
    if not x_admin_secret or not hmac.compare_digest(x_admin_secret, settings.admin_backfill_secret):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Secret header")


@router.post(
    "/backfill-payment-links",
    summary="Generate missing Razorpay payment links for last month's fee records",
    response_model=BackfillPaymentLinksResponse,
    dependencies=[Depends(_verify_admin_secret)],
)
async def backfill_payment_links(
    request: BackfillPaymentLinksRequest,
    fee_service: FeeServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """Manual trigger for the same backfill logic the daily scheduled job runs.

    Always targets last calendar month. Pass institute_id to scope the sweep to
    one institute; omit it to sweep every institute with a connected Razorpay
    account.
    """
    try:
        return await fee_service.backfill_missing_payment_links(
            db=db, institute_id=request.institute_id, month=None
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Backfill failed — check logs")
