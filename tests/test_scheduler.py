"""
Unit tests for scheduler.py — the in-process daily payment-link backfill job.

The job itself (start_scheduler/shutdown_scheduler) is infrastructure glue and
isn't unit-tested here; ENABLE_SCHEDULER=false in conftest.py keeps it from
ever starting during the test suite. What IS tested is the job body
(run_payment_link_backfill), including the Postgres advisory lock guard.
"""

from unittest.mock import AsyncMock, MagicMock, patch


async def test_run_payment_link_backfill_calls_service_when_not_postgres():
    with patch("scheduler._IS_POSTGRES", False):
        mock_db = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("scheduler.AsyncSessionLocal", return_value=mock_cm):
            with patch("scheduler.FeeService") as mock_fee_service_cls:
                mock_fee_service_cls.return_value.backfill_missing_payment_links = AsyncMock(
                    return_value={"checked": 0}
                )

                from scheduler import run_payment_link_backfill

                await run_payment_link_backfill()

                mock_fee_service_cls.return_value.backfill_missing_payment_links.assert_called_once_with(
                    mock_db
                )


async def test_run_payment_link_backfill_skips_when_postgres_lock_not_acquired():
    with patch("scheduler._IS_POSTGRES", True):
        mock_db = AsyncMock()
        lock_result = MagicMock()
        lock_result.scalar.return_value = False
        mock_db.execute = AsyncMock(return_value=lock_result)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("scheduler.AsyncSessionLocal", return_value=mock_cm):
            with patch("scheduler.FeeService") as mock_fee_service_cls:
                from scheduler import run_payment_link_backfill

                await run_payment_link_backfill()

                mock_fee_service_cls.return_value.backfill_missing_payment_links.assert_not_called()


async def test_run_payment_link_backfill_runs_and_unlocks_when_postgres_lock_acquired():
    with patch("scheduler._IS_POSTGRES", True):
        mock_db = AsyncMock()
        lock_result = MagicMock()
        lock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=lock_result)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("scheduler.AsyncSessionLocal", return_value=mock_cm):
            with patch("scheduler.FeeService") as mock_fee_service_cls:
                mock_fee_service_cls.return_value.backfill_missing_payment_links = AsyncMock(
                    return_value={"checked": 1}
                )

                from scheduler import run_payment_link_backfill

                await run_payment_link_backfill()

                mock_fee_service_cls.return_value.backfill_missing_payment_links.assert_called_once_with(
                    mock_db
                )
                # pg_try_advisory_lock, then pg_advisory_unlock
                assert mock_db.execute.call_count == 2
