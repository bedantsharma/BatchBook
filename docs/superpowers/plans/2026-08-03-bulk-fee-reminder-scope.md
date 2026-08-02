# Bulk Fee Reminder — Batch Scoping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `POST /fee/remind-all` optionally scope its bulk WhatsApp fee-reminder send to a single batch, via a new optional `batch_id` query parameter, instead of only ever sending institute-wide.

**Architecture:** One route handler (`send_fee_reminders_for_all` in `routes/fee_route.py`) gains an optional `batch_id: int | None` query param. When set, it's validated against the caller's institute with the existing `_verify_batch_belongs_to_institute` helper, then added as one more `.where()` clause on the query the handler already builds. No new files, no service/repository layer changes — this spec was approved at `docs/superpowers/specs/2026-08-03-bulk-fee-reminder-scope-design.md`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, pytest (async mode `auto`), `aiosqlite` in-memory test DB via `tests/conftest.py`.

## Global Constraints

- Package manager: `uv` — use `uv run pytest`, not bare `pytest`.
- Linter: `ruff`, line length 100, Python 3.14 target.
- Test runner: `pytest`, async mode `auto` — no `@pytest.mark.asyncio` needed, but existing tests in this file don't use it either (rely on `pytest-asyncio` auto mode), so match that.
- Follow this project's CLAUDE.md rule: run `gitnexus_impact({target: "send_fee_reminders_for_all", direction: "upstream"})` before editing the function. **Already run during planning: risk = LOW, 0 upstream callers (it's a route handler, only reached via HTTP), 0 processes/modules affected.** No need to re-run unless the plan changes.
- Run `gitnexus_detect_changes()` before committing, per CLAUDE.md.

---

### Task 1: Add `batch_id` scoping to `POST /fee/remind-all`

**Files:**
- Modify: `routes/fee_route.py` (function `send_fee_reminders_for_all`, currently lines 519–599)
- Test: `tests/test_fee_routes.py`

**Interfaces:**
- Consumes: existing `_resolve_institute_id`, `_verify_batch_belongs_to_institute`, `_parse_month` helpers already defined earlier in `routes/fee_route.py`; `services.notification_service.dispatch_in_background` (async, `**kwargs`); `services.notification_service._body(*texts) -> list[dict]`.
- Produces: `POST /fee/remind-all` now accepts an optional `batch_id: int | None` query param (in addition to the existing required `month: str`). Response JSON gains a `batch_id` key (`null` when the param was omitted). No other route in the file depends on this handler's internals.

- [ ] **Step 1: Write the failing tests**

Open `tests/test_fee_routes.py`. Update the import block at the top of the file from:

```python
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.batch_base import BatchSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service
```

to:

```python
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.batch_base import BatchSchema, BatchStatus
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from services import notification_service
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service
```

Then append this whole block to the **end** of `tests/test_fee_routes.py`:

```python
# ─── POST /fee/remind-all ─────────────────────────────────────────────────────


def _seed_batch(institute_id, name="Class 10 Maths"):
    return BatchSchema(
        institute_id=institute_id,
        name=name,
        subject="Maths",
        start_time=time(16, 0),
        end_time=time(17, 0),
        days_of_week=["MON", "WED", "FRI"],
        max_capacity=30,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )


def _seed_parent(phone_number, name, verified=True):
    return ParentSchema(
        phone_number=phone_number,
        name=name,
        user_id=uuid4() if verified else None,
    )


def _seed_student(name, parent_id=None, institute_id=None):
    return StudentSchema(name=name, parent_id=parent_id, institute_id=institute_id)


def _seed_enrollment(student_id, batch_id, due_day=5):
    return EnrollmentSchema(student_id=student_id, batch_id=batch_id, due_day=due_day)


def _seed_fee_record(
    enrollment_id,
    month=date(2026, 5, 1),
    amount_due=Decimal("1500.00"),
    amount_paid=Decimal("0"),
    status=FeeStatus.NOT_PAID,
):
    return FeeRecordSchema(
        enrollment_id=enrollment_id,
        month=month,
        amount_due=amount_due,
        amount_paid=amount_paid,
        status=status,
    )


@pytest.fixture
def fake_dispatch(monkeypatch):
    calls = []

    async def _fake(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(notification_service, "dispatch_in_background", _fake)
    return calls


def _setup_remind_all_auth(db_session, teacher_id, owner_id=1, institute_id=10):
    """Mock auth/institute resolution the same way other tests in this file do,
    but leave the DB itself real so the route's own query runs for real."""
    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    owner_svc.get_owner_by_teacher_id = AsyncMock(
        return_value=_make_owner(teacher_id, owner_id)
    )

    institute = _make_institute(owner_id, institute_id)
    institute.join_code = None  # keep join_url building deterministic (None)

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.get_by_owner_id = AsyncMock(return_value=institute)
    institute_svc.institute_repo = MagicMock()
    institute_svc.institute_repo.get_by_id = AsyncMock(return_value=institute)

    return owner_svc, institute_svc


async def test_remind_all_institute_wide_queues_unpaid_record(
    client, db_session, fake_dispatch
):
    teacher_id = uuid4()
    owner_svc, institute_svc = _setup_remind_all_auth(db_session, teacher_id)

    batch = _seed_batch(institute_id=10)
    db_session.add(batch)
    await db_session.flush()

    parent = _seed_parent("9876543210", "Verified Parent")
    db_session.add(parent)
    await db_session.flush()

    student = _seed_student("Rahul", parent_id=parent.id, institute_id=10)
    db_session.add(student)
    await db_session.flush()

    enrollment = _seed_enrollment(student.id, batch.id)
    db_session.add(enrollment)
    await db_session.flush()

    fee_record = _seed_fee_record(enrollment.id)
    db_session.add(fee_record)
    await db_session.commit()

    fee_svc = MagicMock(spec=FeeService)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    resp = await client.post(
        "/fee/remind-all",
        params={"month": "2026-05"},
        headers={"authorization": "Bearer test-token"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 202
    data = resp.json()
    assert data["detail"] == "1 reminder(s) queued"
    assert data["batch_id"] is None
    assert len(fake_dispatch) == 1
    assert fake_dispatch[0]["student_id"] == student.id


async def test_remind_all_scoped_to_batch_excludes_other_batches(
    client, db_session, fake_dispatch
):
    teacher_id = uuid4()
    owner_svc, institute_svc = _setup_remind_all_auth(db_session, teacher_id)

    batch_a = _seed_batch(institute_id=10, name="Batch A")
    batch_b = _seed_batch(institute_id=10, name="Batch B")
    db_session.add_all([batch_a, batch_b])
    await db_session.flush()

    parent_a = _seed_parent("9876543210", "Parent A")
    parent_b = _seed_parent("9876543211", "Parent B")
    db_session.add_all([parent_a, parent_b])
    await db_session.flush()

    student_a = _seed_student("Student A", parent_id=parent_a.id, institute_id=10)
    student_b = _seed_student("Student B", parent_id=parent_b.id, institute_id=10)
    db_session.add_all([student_a, student_b])
    await db_session.flush()

    enrollment_a = _seed_enrollment(student_a.id, batch_a.id)
    enrollment_b = _seed_enrollment(student_b.id, batch_b.id)
    db_session.add_all([enrollment_a, enrollment_b])
    await db_session.flush()

    db_session.add_all(
        [_seed_fee_record(enrollment_a.id), _seed_fee_record(enrollment_b.id)]
    )
    await db_session.commit()

    fee_svc = MagicMock(spec=FeeService)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    resp = await client.post(
        "/fee/remind-all",
        params={"month": "2026-05", "batch_id": batch_a.id},
        headers={"authorization": "Bearer test-token"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 202
    data = resp.json()
    assert data["detail"] == "1 reminder(s) queued"
    assert data["batch_id"] == batch_a.id
    assert len(fake_dispatch) == 1
    assert fake_dispatch[0]["student_id"] == student_a.id


async def test_remind_all_batch_in_other_institute_returns_403(
    client, db_session, fake_dispatch
):
    teacher_id = uuid4()
    owner_svc, institute_svc = _setup_remind_all_auth(db_session, teacher_id, institute_id=10)

    foreign_batch = _seed_batch(institute_id=99, name="Someone Else's Batch")
    db_session.add(foreign_batch)
    await db_session.commit()

    fee_svc = MagicMock(spec=FeeService)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    resp = await client.post(
        "/fee/remind-all",
        params={"month": "2026-05", "batch_id": foreign_batch.id},
        headers={"authorization": "Bearer test-token"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 403
    assert len(fake_dispatch) == 0


async def test_remind_all_nonexistent_batch_returns_404(client, db_session, fake_dispatch):
    teacher_id = uuid4()
    owner_svc, institute_svc = _setup_remind_all_auth(db_session, teacher_id)

    fee_svc = MagicMock(spec=FeeService)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    resp = await client.post(
        "/fee/remind-all",
        params={"month": "2026-05", "batch_id": 999999},
        headers={"authorization": "Bearer test-token"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 404
    assert len(fake_dispatch) == 0


async def test_remind_all_skips_record_with_no_verified_phone(
    client, db_session, fake_dispatch
):
    teacher_id = uuid4()
    owner_svc, institute_svc = _setup_remind_all_auth(db_session, teacher_id)

    batch = _seed_batch(institute_id=10)
    db_session.add(batch)
    await db_session.flush()

    parent = _seed_parent("9876543210", "Verified Parent")
    db_session.add(parent)
    await db_session.flush()

    student_with_parent = _seed_student("Has Parent", parent_id=parent.id, institute_id=10)
    student_without_parent = _seed_student("No Parent", parent_id=None, institute_id=10)
    db_session.add_all([student_with_parent, student_without_parent])
    await db_session.flush()

    enrollment_with_parent = _seed_enrollment(student_with_parent.id, batch.id)
    enrollment_without_parent = _seed_enrollment(student_without_parent.id, batch.id)
    db_session.add_all([enrollment_with_parent, enrollment_without_parent])
    await db_session.flush()

    db_session.add_all(
        [
            _seed_fee_record(enrollment_with_parent.id),
            _seed_fee_record(enrollment_without_parent.id),
        ]
    )
    await db_session.commit()

    fee_svc = MagicMock(spec=FeeService)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    resp = await client.post(
        "/fee/remind-all",
        params={"month": "2026-05", "batch_id": batch.id},
        headers={"authorization": "Bearer test-token"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 202
    data = resp.json()
    assert data["detail"] == "1 reminder(s) queued"
    assert len(fake_dispatch) == 1
    assert fake_dispatch[0]["student_id"] == student_with_parent.id
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_fee_routes.py -k remind_all -v`
Expected: All 5 new tests FAIL. The scoping/403/404 tests fail because `batch_id` isn't a recognized query param yet (FastAPI will just ignore unknown query params, so those requests behave as institute-wide and don't return 403/404 — assertions on status code and `batch_id` in the response body fail). The institute-wide test fails because the response has no `batch_id` key yet.

- [ ] **Step 3: Implement the route change**

In `routes/fee_route.py`, replace the entire `send_fee_reminders_for_all` function (the `POST /fee/remind-all` handler, currently the last function in the file) with:

```python
@router.post(
    "/remind-all",
    summary="Send WhatsApp fee reminders to all parents with unpaid fees for a month",
    status_code=202,
)
async def send_fee_reminders_for_all(
    background_tasks: BackgroundTasks,
    fee_service: FeeServiceDep,
    owner_service: OwnerServiceDep,
    institute_service: InstituteServiceDep,
    month: str = Query(..., examples=["2026-05"], description="Month in YYYY-MM format"),
    batch_id: int | None = Query(
        None,
        description="If set, only remind students in this batch. Omit for institute-wide.",
    ),
    db: AsyncSession = Depends(get_db),
    owner_user_id: UUID = Depends(_get_current_owner_user_id),
):
    """Queue WhatsApp fee_reminder messages for every unpaid or partially-paid record
    in the institute (or, if ``batch_id`` is given, in that batch only) for the given month.

    Returns 202 Accepted with the count of reminders queued. Each WhatsApp call
    happens in the background so this endpoint returns instantly regardless of
    how many reminders are sent.
    """
    from models.batch_base import BatchSchema
    from models.fee_record_base import FeeStatus
    from models.notification_base import NotificationType
    from models.parent_base import ParentSchema
    from models.student_base import StudentSchema
    from services.notification_service import _body, dispatch_in_background

    institute_id = await _resolve_institute_id(
        db, owner_user_id, owner_service, institute_service
    )
    month_date = _parse_month(month)

    if batch_id is not None:
        await _verify_batch_belongs_to_institute(db, batch_id, institute_id)

    inst = await institute_service.institute_repo.get_by_id(db, institute_id)
    join_url = (
        f"{get_settings().frontend_base_url}/join/{inst.join_code}"
        if inst and inst.join_code
        else None
    )

    query = (
        select(FeeRecordSchema, EnrollmentSchema, StudentSchema, ParentSchema, BatchSchema)
        .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
        .join(StudentSchema, EnrollmentSchema.student_id == StudentSchema.id)
        .outerjoin(ParentSchema, StudentSchema.parent_id == ParentSchema.id)
        .join(BatchSchema, EnrollmentSchema.batch_id == BatchSchema.id)
        .where(
            BatchSchema.institute_id == institute_id,
            FeeRecordSchema.month == month_date,
            FeeRecordSchema.status != FeeStatus.FULLY_PAID,
        )
    )
    if batch_id is not None:
        query = query.where(EnrollmentSchema.batch_id == batch_id)

    result = await db.execute(query)

    queued = 0
    for fee_record, enrollment, student, parent, batch in result.all():
        if not parent or not parent.phone_number:
            continue
        amount_pending = fee_record.amount_due - fee_record.amount_paid
        due_date = f"{enrollment.due_day} {fee_record.month.strftime('%b %Y')}"
        link_text = fee_record.payment_link or "Contact your institute"
        amount_str = (
            f"{int(amount_pending):,}"
            if amount_pending == int(amount_pending)
            else f"{float(amount_pending):.2f}"
        )
        components = _body(
            student.name or "Student", amount_str, batch.name, due_date, link_text
        )
        background_tasks.add_task(
            dispatch_in_background,
            parent=parent,
            student_id=student.id,
            institute_id=institute_id,
            type=NotificationType.FEE_REMINDER,
            template_name="fee_reminder",
            components=components,
            join_url=join_url,
        )
        queued += 1

    return {"detail": f"{queued} reminder(s) queued", "month": month, "batch_id": batch_id}
```

The only behavioral changes from the existing handler: the new `batch_id` parameter, the conditional `_verify_batch_belongs_to_institute` call, the conditional `.where(EnrollmentSchema.batch_id == batch_id)`, and `batch_id` added to the returned dict. Everything else (query joins/filters, skip-on-no-phone logic, `dispatch_in_background` call shape) is unchanged.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/test_fee_routes.py -k remind_all -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run the full fee route test suite to check for regressions**

Run: `uv run pytest tests/test_fee_routes.py -v`
Expected: All tests PASS (the pre-existing tests in this file plus the 5 new ones).

- [ ] **Step 6: Lint**

Run: `uv run ruff check routes/fee_route.py tests/test_fee_routes.py`
Expected: No errors. If ruff reformats anything (e.g. import ordering), re-run the test suite from Step 5 to confirm nothing broke.

- [ ] **Step 7: Detect changes via GitNexus before committing**

Run the `mcp__gitnexus__detect_changes` MCP tool (scope: `unstaged`, repo: `BatchBook`) and confirm the only affected symbol is `send_fee_reminders_for_all` in `routes/fee_route.py`, with no unexpected affected processes. This satisfies this project's CLAUDE.md pre-commit rule.

- [ ] **Step 8: Commit**

```bash
git add routes/fee_route.py tests/test_fee_routes.py
git commit -m "feat(fee): allow /fee/remind-all to scope reminders to a single batch"
```

---

## Self-Review Notes

- **Spec coverage:** §3 (route signature) → Step 3. §4 (response shape) → Step 3's return statement + Step 1's assertions. §5 (error handling) → Steps 1/2's 403/404 tests, all reusing existing helpers so no new error paths were introduced. §6 (testing) → Step 1 covers all 5 scenarios listed in the spec. §7 (out of scope) → respected: no changes to `/fee/remind/{record_id}`, no frontend changes, no new dedup guard.
- **Type consistency:** `batch_id: int | None` used consistently in the route signature, the `_verify_batch_belongs_to_institute(db, batch_id, institute_id)` call (existing helper signature: `(db: AsyncSession, batch_id: int, institute_id: int) -> BatchSchema`, confirmed against `routes/fee_route.py:69-81`), and the response dict. Test helpers (`_seed_batch`, `_seed_parent`, `_seed_student`, `_seed_enrollment`, `_seed_fee_record`) return real ORM instances whose attributes (`.id`, `.name`, etc.) are used consistently across all 5 tests.
- **Single task is correct sizing here:** this is one cohesive route change with one test file touched: the route can't meaningfully be split into a reviewable sub-piece smaller than "add the param, filter, and response field, with tests."
