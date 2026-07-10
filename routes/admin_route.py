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
from routes.responses.seed_demo_accounts_response import SeedDemoAccountsResponse
from services.demo_seed_service import DemoSeedService, get_demo_seed_service
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service

router = APIRouter(prefix="/admin")

FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]
DemoSeedServiceDep = Annotated[DemoSeedService, Depends(get_demo_seed_service)]


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


@router.post(
    "/seed-demo-accounts",
    summary="Seed the Play Store reviewer test accounts (owner 9999999999 + student 9999999998)",
    response_model=SeedDemoAccountsResponse,
    dependencies=[Depends(_verify_admin_secret)],
)
async def seed_demo_accounts(
    demo_seed_service: DemoSeedServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """Idempotent — safe to re-run any time Test-OTP-backed reviewer data drifts.

    Creates/links Owner (9999999999) -> Institute -> 2 Batches, and Parent+Student
    (9999999998) -> 2 Enrollments -> ClassSessions/Attendance/FeeRecords, using the
    same production service methods real signups go through.

    Note: session/fee dates are computed relative to today, so re-running on a
    later calendar day may add new non-duplicate rows instead of all-zero counters."""
    try:
        result = await demo_seed_service.seed(db)
    except Exception as e:
        logger.exception("Demo seed failed")
        raise HTTPException(status_code=500, detail="Demo seed failed — check logs") from e
    return SeedDemoAccountsResponse(
        owner_created=result.owner_created,
        institute_created=result.institute_created,
        batches_created=result.batches_created,
        student_created=result.student_created,
        sessions_created=result.sessions_created,
        fee_records_created=result.fee_records_created,
    )
