import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.session import get_db
from routes.requests.backfill_payment_links_request import BackfillPaymentLinksRequest
from routes.requests.generate_site_request import GenerateSiteRequest
from routes.responses.backfill_payment_links_response import BackfillPaymentLinksResponse
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service

router = APIRouter(prefix="/admin")

FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


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


@router.post(
    "/institute/{institute_id}/generate-site",
    summary="Generate/update a Tier 2 site-generator page for an institute",
    dependencies=[Depends(_verify_admin_secret)],
)
async def generate_site(
    institute_id: int,
    request: GenerateSiteRequest,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """Admin-only (X-Admin-Secret) — same pattern as backfill-payment-links.
    BatchBook ops calls this after collecting an owner's site content over
    WhatsApp/call, for owners who won't self-serve a Tier 1 site themselves."""
    try:
        institute = await institute_service.generate_site(
            db,
            institute_id,
            slug=request.slug,
            address=request.address,
            phone_public=request.phone_public,
            email_public=request.email_public,
            description=request.description,
            course_fee_display=request.course_fee_display,
            color_scheme=request.color_scheme,
        )
    except ValueError as e:
        message = str(e)
        status_code = 404 if message.startswith("No institute found") else 400
        raise HTTPException(status_code=status_code, detail=message) from e
    return {"public_url": f"https://{institute.slug}.batchbook.in"}
