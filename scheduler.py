"""In-process daily job that backfills missing Razorpay payment links.

Runs inside the FastAPI process via APScheduler. Guarded by a Postgres
advisory lock so the two prod uvicorn workers (and any future horizontal
replicas) don't run the same sweep twice.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import text

from db.session import AsyncSessionLocal, engine
from services.fee_service import FeeService

_ADVISORY_LOCK_KEY = 872_364_501  # arbitrary constant unique to this job
_IS_POSTGRES = engine.dialect.name == "postgresql"

_scheduler: AsyncIOScheduler | None = None


async def run_payment_link_backfill() -> None:
    """Job body: acquire the advisory lock (Postgres only), run the backfill, release it."""
    async with AsyncSessionLocal() as db:
        if _IS_POSTGRES:
            result = await db.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
            )
            if not result.scalar():
                logger.info(
                    "Payment link backfill: another worker holds the lock, skipping this run"
                )
                return

        try:
            summary = await FeeService().backfill_missing_payment_links(db)
            logger.info(f"Payment link backfill completed: {summary}")
        finally:
            if _IS_POSTGRES:
                await db.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY}
                )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_payment_link_backfill,
        trigger=IntervalTrigger(hours=24),
        id="payment_link_backfill_daily",
        replace_existing=True,
    )
    _scheduler.start()
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
