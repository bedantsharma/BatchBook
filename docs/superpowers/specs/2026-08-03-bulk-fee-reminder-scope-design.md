# Bulk Fee Reminder — Batch Scoping — Design

**Date:** 2026-08-03
**Trigger:** The owner wants to send fee reminders in bulk to either one batch or the whole
institute. Today `POST /fee/remind-all` already sends institute-wide, but there is no way to
scope a bulk send to a single batch — the only per-batch option is the single-record endpoint
`POST /fee/remind/{record_id}`, which the owner would have to call once per unpaid student.
**Repos affected:** `BatchBook` (backend only). No frontend/UI change is in scope for this doc.

---

## 1. Problem

`routes/fee_route.py` has two reminder endpoints:

- `POST /fee/remind/{record_id}` — sends one WhatsApp `fee_reminder` for a single fee record.
- `POST /fee/remind-all?month=YYYY-MM` — queries every unpaid/partially-paid `FeeRecord` across
  the whole institute for a given month and queues a reminder for each.

There is no bulk option scoped to a single batch (e.g. "remind everyone in the 10th Maths batch
who hasn't paid this month"). Building that today means the owner calls the single-record
endpoint once per student, which doesn't scale past a handful of students.

## 2. Approach

Extend the existing `POST /fee/remind-all` handler with an optional `batch_id` query parameter,
rather than adding a parallel endpoint. The two paths already share the same query shape (join
`FeeRecord → Enrollment → Student → Parent → Batch`, filter unpaid/partially-paid for a month,
loop and queue `dispatch_in_background`) — a batch scope is just one more `WHERE` clause on the
same query.

- `batch_id` omitted → institute-wide, byte-for-byte the current behavior.
- `batch_id` provided → validated against the caller's institute via the existing
  `_verify_batch_belongs_to_institute` helper (same 403/404 semantics used everywhere else in
  this file), then the query adds `EnrollmentSchema.batch_id == batch_id`.

No new files, no service/repository changes — the filtering happens inline in the route handler,
matching how the existing query is already built there.

## 3. Route signature

```python
@router.post("/remind-all", summary=..., status_code=202)
async def send_fee_reminders_for_all(
    background_tasks: BackgroundTasks,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    month: str = Query(..., examples=["2026-05"], description="Month in YYYY-MM format"),
    batch_id: int | None = Query(
        None, description="If set, only remind students in this batch. Omit for institute-wide."
    ),
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
```

Behavior:
1. Resolve `institute_id` as today.
2. If `batch_id` is not `None`, call `await _verify_batch_belongs_to_institute(db, batch_id, institute_id)` — raises 404 if the batch doesn't exist, 403 if it belongs to a different institute.
3. Build the query exactly as today, and additionally apply `.where(EnrollmentSchema.batch_id == batch_id)` only when `batch_id is not None`.
4. Loop/queue logic (skip records with no verified parent phone, build `_body(...)`, `background_tasks.add_task(dispatch_in_background, ...)`) is unchanged.

## 4. Response

```json
{"detail": "N reminder(s) queued", "month": "2026-05", "batch_id": 12}
```

`batch_id` is `null` in the response when the call was institute-wide (param omitted). This is
an additive field — existing institute-wide callers get the same `detail`/`month` keys they get
today, plus one new key.

## 5. Error handling

Reuses existing patterns already in this file — no new error paths:
- Bad `month` format → 422 (existing `_parse_month` helper).
- `batch_id` set but batch not found → 404 (`_verify_batch_belongs_to_institute`).
- `batch_id` set but belongs to another institute → 403 (`_verify_batch_belongs_to_institute`).
- No institute set up yet → 404 (`_resolve_institute_id`, existing).
- Records with no parent / no verified phone are silently skipped and not counted, same as today.

## 6. Testing

`tests/test_fee_routes.py` currently has zero coverage for either `/fee/remind*` endpoint. Add
route-level tests for the extended `/fee/remind-all` only (single-record endpoint coverage is
explicitly out of scope for this change):

1. Institute-wide call (`batch_id` omitted) queues reminders for unpaid records across all
   batches in the institute — behavior unchanged from before this change.
2. `batch_id` provided queues reminders only for unpaid records in that batch, not other batches
   in the same institute.
3. `batch_id` belonging to a different institute → 403.
4. Nonexistent `batch_id` → 404.
5. A matched record whose parent has no phone number (or no parent) is skipped and not counted
   in the returned total, whether scoped or institute-wide.

Tests use the existing `aiosqlite` in-memory test DB / `conftest.py` fixtures already used by the
rest of `test_fee_routes.py`, mocking `dispatch_in_background` the way other notification-adjacent
tests in this suite already do (see `tests/test_notification_dispatch.py` for the pattern).

## 7. Out of scope

- No changes to `/fee/remind/{record_id}` (single-record) or its test coverage.
- No frontend/UI changes.
- No new dedup/rate-limit guard against re-sending a reminder already sent today — neither
  existing reminder endpoint has this, and this change doesn't introduce new risk beyond what
  `/fee/remind-all` already carries (an owner can already re-trigger institute-wide sends
  repeatedly).
