# Payment Link Callback + Institute-Scoped Backfill

Date: 2026-07-02

## Problem

Two gaps in the fee-collection flow:

1. When a parent pays via a Razorpay payment link, Razorpay has no `callback_url` to
   redirect them back to, so they're left staring at Razorpay's own confirmation page
   instead of a BatchBook screen.
2. Payment links are only ever created on-demand (owner clicks "get link" or "remind").
   If an owner connects their Razorpay account *after* fee records already exist for a
   month, those existing records never get a link unless the owner manually revisits
   every one. There's no way to backfill missing links in bulk, and no recurring job to
   catch this automatically.

Investigating gap 2 surfaced a pre-existing gap 3: `InstituteSchema` stores each
institute's own connected Razorpay credentials (`razorpay_key_id`,
`razorpay_key_secret_encrypted`), but `generate_payment_link` has never used them —
every payment link today is created via the platform's global `.env` Razorpay client,
regardless of which institute it belongs to. This spec fixes that as a prerequisite,
since "does this institute have Razorpay creds" only matters if links are actually
created under that institute's own account.

## Decisions

- **Per-institute Razorpay client.** Payment links must be created using the owning
  institute's own connected Razorpay account, not the platform's global client.
- **Cron mechanism.** In-process APScheduler running inside the FastAPI app (not an
  external Render Cron Job), guarded by a Postgres advisory lock so the two prod
  uvicorn workers (and any future horizontal replicas) don't run the job twice.
- **Manual trigger auth.** A static admin-secret header (`X-Admin-Secret` /
  `ADMIN_BACKFILL_SECRET` env var) — no owner-scoped auth, since this operates across
  institutes.
- **Institute lookup for manual trigger.** `institute_id` only (no name-based lookup —
  names aren't guaranteed unique).
- **Success page scope.** Purely cosmetic. There is no Razorpay webhook in this
  codebase — `FeeRecord.status` only changes via the owner's manual
  `PATCH /fee/record/{id}/pay`. The success page is a friendly "we got it, your
  institute will confirm shortly" screen, not a real-time payment verification. A
  webhook-driven auto-confirmation is out of scope for this change.
- **"Last month" is computed at run time**, not a fixed date — always the calendar
  month before whatever "today" is when the job/endpoint runs.

## Section 1 — Payment link callback + success page

**Backend:**
- New setting `frontend_base_url: str` in `config.py` (e.g. `https://batchbook.in` in
  prod, `http://localhost:5173` in dev), added to `.env`.
- This also replaces the two places `fee_route.py` currently hardcodes
  `"https://batchbook.in/join/..."` (in `send_fee_reminder_for_record` and
  `send_fee_reminders_for_all`) with `settings.frontend_base_url` — one source of truth.
- `FeeService.generate_payment_link` adds to the Razorpay payment-link payload:
  ```python
  data["callback_url"] = f"{settings.frontend_base_url}/payment-success"
  data["callback_method"] = "get"
  ```

**Frontend (`batchbookui/`):**
- New route `/payment-success` in `App.jsx` → new `PaymentSuccess.jsx` component.
- Dark Material-3 themed page with an animated checkmark (CSS/SVG stroke-draw
  animation, no new dependency) and static copy: "Payment received — your institute
  will confirm shortly."
- No API call, no signature verification — see "Success page scope" above.
- Committed and pushed from within the `batchbookui/` submodule per the repo's
  submodule rules, then the parent repo's submodule pointer is bumped separately.

## Section 2 — Per-institute Razorpay client

- New helper in `clients/razorpay_client.py`:
  ```python
  def build_institute_razorpay_client(institute: InstituteSchema) -> razorpay.Client | None
  ```
  Returns `None` if `institute.razorpay_status != RazorpayStatus.CONNECTED` or either
  credential field is missing. Otherwise decrypts the secret via
  `crypto_service.decrypt_secret` and returns
  `razorpay.Client(auth=(institute.razorpay_key_id, decrypted_secret))`.
- `GET /fee/record/{record_id}/payment-link` (existing route in `fee_route.py`) changes
  to resolve the record's institute and call `build_institute_razorpay_client` instead
  of the global `get_razorpay_client()`. If it returns `None`, respond `503`:
  `"Razorpay not connected for this institute — connect it in Owner → Payouts first"`.
  - **Behavior change:** today this endpoint silently succeeds via the platform's
    global key for every institute. After this change, an institute that hasn't
    connected its own Razorpay account gets a clear 503 instead of a link created
    under the platform's account.
- `FeeService.generate_payment_link`'s signature is unchanged — it still receives an
  already-built `razorpay_client`. Only what the caller builds changes. Keeps the
  service decoupled from crypto/institute lookup concerns.
- The global `get_razorpay_client()` (`clients/razorpay_client.py`) is left as-is and
  unused after this change is complete — not deleted, since removing platform-wide
  Razorpay config might still be wanted for other future use (e.g. platform's own
  subscription billing). Out of scope to decide now.

## Section 3 — Backfill logic (shared by cron + manual endpoint)

New method on `FeeService`:

```python
async def backfill_missing_payment_links(
    self, db: AsyncSession, institute_id: int | None, month: date | None
) -> dict
```

- `month` defaults to the first day of last calendar month relative to `date.today()`
  when not given. Both the cron path and the manual endpoint always call this with
  `month=None` — last month is the only supported target for both, per the original
  ask. The `month` parameter exists on the method itself (rather than being computed
  inline) purely so unit tests can pass an explicit month instead of depending on
  wall-clock time.
- Query: `FeeRecordSchema` joined through `EnrollmentSchema → BatchSchema →
  InstituteSchema`, filtered to `month == target_month`, `payment_link IS NULL`,
  `status != FeeStatus.FULLY_PAID`. If `institute_id` is given, restrict to that
  institute; otherwise all institutes (cron's global sweep).
- Group matching records by institute. For each institute:
  - Build its Razorpay client via `build_institute_razorpay_client`.
  - If `None` → skip all its records, increment `skipped_no_razorpay` by the count.
  - Otherwise call the existing `generate_payment_link` once per record. A failure on
    one record (Razorpay API error, etc.) is caught, logged, and counted in `failed` —
    it does not abort the rest of the batch.
- Returns:
  ```python
  {
      "month": "2026-06-01",
      "checked": int,
      "generated": int,
      "skipped_no_razorpay": int,
      "failed": int,
      "errors": [{"record_id": int, "error": str}, ...],
  }
  ```

## Section 4 — Scheduler wiring + manual admin endpoint

**Scheduler (`app.py` lifespan):**
- Add `apscheduler` dependency (`uv add apscheduler`).
- `AsyncIOScheduler` with a daily job (`IntervalTrigger(hours=24)`) calling
  `FeeService().backfill_missing_payment_links(db, institute_id=None, month=None)`
  against a fresh session from `AsyncSessionLocal()`.
- New setting `enable_scheduler: bool = True` in `config.py`. The scheduler is only
  started in the lifespan if this is `True`. `tests/conftest.py` sets
  `ENABLE_SCHEDULER=false` so the test suite never starts background jobs.
- Cross-worker guard: before running the job body, attempt
  `SELECT pg_try_advisory_lock(:key)` with a fixed arbitrary key constant for this job.
  If it returns `false`, another worker/replica already holds it — skip this run and
  return early. Release the lock (`pg_advisory_unlock`) when the job finishes, in a
  `finally` block.
- Scheduler is shut down (`scheduler.shutdown()`) in the lifespan's teardown (after
  `yield`).

**Manual endpoint (new `routes/admin_route.py`, prefix `/admin`):**
- `POST /admin/backfill-payment-links`
  - Body: `{"institute_id": int | None}` — omit/`null` to sweep all institutes.
  - Auth: header `X-Admin-Secret` must match `settings.admin_backfill_secret`
    (`ADMIN_BACKFILL_SECRET` env var). Missing/mismatched → `401`.
  - Calls `backfill_missing_payment_links(db, institute_id=body.institute_id,
    month=None)` synchronously and returns the summary dict — institute/record counts
    are small enough at this stage that a background task isn't needed.
- Registered in `app.py` alongside the other routers.

## New environment variables

Add to `config.py` (`Settings`) and `.env`:

| Var | Purpose |
|---|---|
| `FRONTEND_BASE_URL` | Base URL used to build `callback_url` and (replacing hardcoded strings) join links. |
| `ENABLE_SCHEDULER` | `true`/`false` — gates whether the in-process APScheduler starts. Defaults `true`; test suite sets `false`. |
| `ADMIN_BACKFILL_SECRET` | Shared secret required in `X-Admin-Secret` header for the manual backfill endpoint. |

## Testing plan

- `test_fee_service.py`: `generate_payment_link` includes `callback_url`/
  `callback_method` in the payload sent to the (mocked) Razorpay client.
- `test_razorpay_client.py` (new): `build_institute_razorpay_client` returns `None`
  for `NOT_CONNECTED`/`NEEDS_RECONNECT`/missing-creds institutes, and a configured
  client for `CONNECTED` ones (mock `decrypt_secret`).
- `test_fee_routes.py`: `GET /fee/record/{id}/payment-link` returns 503 when the
  institute isn't connected; succeeds when it is (mocking the institute-specific
  client builder).
- `test_fee_service.py`: `backfill_missing_payment_links` — records with an existing
  `payment_link` are skipped; `FULLY_PAID` records are skipped; institutes without
  Razorpay connected are counted under `skipped_no_razorpay`; a Razorpay failure on one
  record doesn't stop others from being processed; `institute_id` filter scopes
  correctly; default month resolves to "last calendar month" relative to a frozen/mocked
  `date.today()`.
- `test_admin_routes.py` (new): missing/wrong `X-Admin-Secret` → 401; correct secret →
  200 with summary; `institute_id` omitted sweeps all institutes.
- Scheduler wiring itself (APScheduler + advisory lock) is not unit-tested — it's
  infrastructure glue verified by `ENABLE_SCHEDULER=false` in tests, plus a manual
  smoke check (start the app locally, confirm the job registers and the advisory lock
  round-trips against the dev DB).
- Frontend: no automated test framework currently exists in `batchbookui/`; verify
  `/payment-success` manually in the browser (dev server) per this repo's existing
  frontend verification practice.

## Out of scope

- Real payment verification via a Razorpay webhook (flagged above as future work).
- Removing/repurposing the platform-wide `.env` Razorpay client.
- Institute name-based lookup for the manual endpoint.
- Backfilling months other than "last month" — neither the cron path nor the manual
  endpoint exposes a way to target a different month; both always operate on last
  month, per the original ask.
