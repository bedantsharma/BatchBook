# Student Onboarding + Notification Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new-student onboarding end-to-end (every student has a name + verified parent), and audit every WhatsApp notification with a verification gate.

**Architecture:** Backend routes all add-student traffic through the existing `POST /enrollment/invite` (creates Parent stub + Student + Enrollment); parents "claim" their stub on OTP login (lookup by phone). A new `Notification` table audits every send; a `dispatch` orchestrator gates parent-facing reminders on verification (`Parent.user_id IS NOT NULL`) and re-sends the invite link when unverified. Frontend switches the Add-Student modal to the invite endpoint, adds an invite-link landing route, and surfaces verification status.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, pytest (aiosqlite); React 19 + Vite + MUI, vitest.

## Global Constraints

- Package manager: `uv` — run commands as `uv run <cmd>`. Never use `pip`/`python` directly.
- Linter: `ruff` (line length 100, Python 3.14). Run `uv run ruff check --fix .` before each commit.
- Tests: `uv run pytest`. Async mode is `auto`.
- "Verified" parent = `Parent.user_id IS NOT NULL`. No new boolean column.
- Notification audit column: Python attribute `meta_data`, DB column name `metadata`, type `JSON`. Stores `{message, institute_id, whatsapp_response}`.
- Frontend changes live in the `batchbookui/` submodule — commit there on branch `feat/student-onboarding-ui`, then bump the pointer in BatchBook (see Task 12). Never `git add batchbookui/` with a trailing slash.
- Every git commit message ends with the Co-Authored-By and Claude-Session trailers used on this branch's first commit.

---

## PART A — BACKEND (BatchBook repo)

### Task 1: Notification model + enums + registration

**Files:**
- Create: `models/notification_base.py`
- Modify: `models/__init__.py`

**Interfaces:**
- Produces: `NotificationSchema` (table `Notification`); `NotificationType` (enum: `FEE_REMINDER`, `FEE_RECEIPT`, `ABSENCE`, `ENROLLMENT_INVITE`); `NotificationStatus` (enum: `SENT`, `SKIPPED_UNVERIFIED`, `FAILED`). Columns: `id, parent_id, student_id, institute_id, type, status, reason, meta_data (col "metadata"), created_at`.

- [ ] **Step 1: Create the model**

`models/notification_base.py`:
```python
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Index, Integer, String

from db.base import Base


class NotificationType(str, PyEnum):
    FEE_REMINDER = "FEE_REMINDER"
    FEE_RECEIPT = "FEE_RECEIPT"
    ABSENCE = "ABSENCE"
    ENROLLMENT_INVITE = "ENROLLMENT_INVITE"


class NotificationStatus(str, PyEnum):
    SENT = "SENT"
    SKIPPED_UNVERIFIED = "SKIPPED_UNVERIFIED"
    FAILED = "FAILED"


class NotificationSchema(Base):
    __tablename__ = "Notification"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    parent_id = Column(Integer, ForeignKey("Parent.id"), nullable=True)
    student_id = Column(Integer, ForeignKey("Student.id"), nullable=True)
    institute_id = Column(Integer, ForeignKey("Institute.id"), nullable=True)
    type = Column(Enum(NotificationType), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False)
    reason = Column(String, nullable=True)
    meta_data = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    __table_args__ = (
        Index("ix_notification_institute_id", "institute_id"),
        Index("ix_notification_student_id", "student_id"),
    )
```

- [ ] **Step 2: Register for Alembic autogenerate**

In `models/__init__.py`, add an import alongside the others:
```python
from models.notification_base import NotificationSchema  # noqa: F401
```

- [ ] **Step 3: Verify it imports**

Run: `uv run python -c "from models import NotificationSchema; print(NotificationSchema.__tablename__)"`
Expected: prints `Notification`

- [ ] **Step 4: Commit**

```bash
uv run ruff check --fix models/
git add models/notification_base.py models/__init__.py
git commit -m "feat: add Notification audit model + enums"
```

---

### Task 2: NotificationRepository

**Files:**
- Create: `repositories/notification_repository.py`
- Test: `tests/test_notification_repository.py`

**Interfaces:**
- Consumes: `NotificationSchema`, `NotificationType`, `NotificationStatus` from Task 1.
- Produces: `NotificationRepository` with `async create(db, notification) -> NotificationSchema` and `async get_latest_by_student_ids(db, student_ids: list[int]) -> dict[int, NotificationSchema]` (maps student_id → most recent notification).

- [ ] **Step 1: Write the failing test**

`tests/test_notification_repository.py`:
```python
import pytest

from models.notification_base import NotificationSchema, NotificationStatus, NotificationType
from repositories.notification_repository import NotificationRepository


@pytest.mark.asyncio
async def test_create_and_latest_by_student(db_session):
    repo = NotificationRepository()
    older = NotificationSchema(
        student_id=1, type=NotificationType.FEE_REMINDER,
        status=NotificationStatus.SENT, meta_data={"message": "a"},
    )
    newer = NotificationSchema(
        student_id=1, type=NotificationType.FEE_REMINDER,
        status=NotificationStatus.SKIPPED_UNVERIFIED, reason="parent number not verified",
        meta_data={"message": "b"},
    )
    await repo.create(db_session, older)
    created = await repo.create(db_session, newer)
    assert created.id is not None

    latest = await repo.get_latest_by_student_ids(db_session, [1, 999])
    assert latest[1].status == NotificationStatus.SKIPPED_UNVERIFIED
    assert 999 not in latest
```

- [ ] **Step 2: Run it, verify it fails**

Run: `uv run pytest tests/test_notification_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: repositories.notification_repository`

- [ ] **Step 3: Implement the repository**

`repositories/notification_repository.py`:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification_base import NotificationSchema


class NotificationRepository:
    async def create(
        self, db: AsyncSession, notification: NotificationSchema
    ) -> NotificationSchema:
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        return notification

    async def get_latest_by_student_ids(
        self, db: AsyncSession, student_ids: list[int]
    ) -> dict[int, NotificationSchema]:
        if not student_ids:
            return {}
        result = await db.execute(
            select(NotificationSchema)
            .where(NotificationSchema.student_id.in_(student_ids))
            .order_by(NotificationSchema.created_at.desc(), NotificationSchema.id.desc())
        )
        latest: dict[int, NotificationSchema] = {}
        for row in result.scalars().all():
            if row.student_id not in latest:
                latest[row.student_id] = row
        return latest
```

- [ ] **Step 4: Run it, verify it passes**

Run: `uv run pytest tests/test_notification_repository.py -v`
Expected: PASS (2 assertions in one test)

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix repositories/ tests/
git add repositories/notification_repository.py tests/test_notification_repository.py
git commit -m "feat: add NotificationRepository"
```

---

### Task 3: Alembic migration for Notification table

**Files:**
- Create: `alembic/versions/<generated>_add_notification_table.py` (autogenerated)

- [ ] **Step 1: Autogenerate the migration**

Run: `uv run alembic revision --autogenerate -m "add notification table"`
Expected: creates a file under `alembic/versions/` whose `upgrade()` calls `op.create_table('Notification', ...)`.

- [ ] **Step 2: Inspect the generated file**

Open the new file. Confirm: `op.create_table('Notification', ...)` with columns `id, parent_id, student_id, institute_id, type, status, reason, metadata, created_at`, the two indexes, and FKs to `Parent`, `Student`, `Institute`. Confirm `downgrade()` drops the table. If autogenerate added unrelated drops/alters from model drift, delete those lines so the migration only creates `Notification` and its indexes.

- [ ] **Step 3: Verify upgrade runs on a scratch SQLite DB**

Run: `uv run python -c "from models import NotificationSchema; from db.base import Base; print('metadata' in [c.name for c in NotificationSchema.__table__.columns])"`
Expected: prints `True` (confirms DB column is named `metadata`).

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: alembic migration for Notification table"
```

---

### Task 4: Fix parent stub-claim + name persistence

**Files:**
- Modify: `services/parent_service.py` (`get_or_create_after_otp`)
- Test: `tests/test_parent_service.py` (create if absent)

**Interfaces:**
- Consumes: `ParentRepository.get_by_user_id`, `get_by_phone`, `update_parent`, `create_parent` (all exist).
- Produces: unchanged signature `get_or_create_after_otp(db, user_id, phone, name) -> ParentSchema`, new behavior: claims an existing stub by phone and persists name.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_parent_service.py` (create the file with these imports if it doesn't exist):
```python
import uuid

import pytest

from models.parent_base import ParentSchema
from repositories.parent_repository import ParentRepository
from services.parent_service import ParentService


@pytest.mark.asyncio
async def test_claims_stub_by_phone_and_sets_name(db_session):
    # Owner-created stub: phone + name, no user_id
    repo = ParentRepository()
    stub = ParentSchema(phone_number="9876543210", name="Asha", user_id=None)
    await repo.create_parent(db_session, stub)

    uid = uuid.uuid4()
    svc = ParentService()
    parent = await svc.get_or_create_after_otp(db_session, uid, "9876543210", name="Asha Devi")

    assert parent.id == stub.id          # same row claimed, not a duplicate
    assert str(parent.user_id) == str(uid)
    assert parent.name == "Asha Devi"    # name updated from OTP step


@pytest.mark.asyncio
async def test_creates_new_parent_when_none_exists(db_session):
    uid = uuid.uuid4()
    svc = ParentService()
    parent = await svc.get_or_create_after_otp(db_session, uid, "9000000000", name="New")
    assert parent.id is not None
    assert parent.name == "New"


@pytest.mark.asyncio
async def test_backfills_name_on_existing_verified_parent(db_session):
    uid = uuid.uuid4()
    repo = ParentRepository()
    existing = ParentSchema(phone_number="9111111111", name=None, user_id=uid)
    await repo.create_parent(db_session, existing)

    svc = ParentService()
    parent = await svc.get_or_create_after_otp(db_session, uid, "9111111111", name="Filled")
    assert parent.name == "Filled"
```

- [ ] **Step 2: Run them, verify they fail**

Run: `uv run pytest tests/test_parent_service.py -v`
Expected: `test_claims_stub_by_phone_and_sets_name` FAILS (currently creates a duplicate / IntegrityError or ignores name).

- [ ] **Step 3: Implement the fix**

Replace `get_or_create_after_otp` in `services/parent_service.py` with:
```python
    async def get_or_create_after_otp(
        self,
        db: AsyncSession,
        user_id: UUID,
        phone: str,
        name: str | None,
    ) -> ParentSchema:
        # 1. Already-verified parent (by Supabase user_id)
        existing = await self.parent_repo.get_by_user_id(db, user_id)
        if existing:
            if name and not existing.name:
                return await self.parent_repo.update_parent(db, existing, {"name": name})
            return existing

        # 2. Owner-created stub (matched by phone, no user_id yet) → claim it
        stub = await self.parent_repo.get_by_phone(db, phone)
        if stub:
            updates: dict = {"user_id": user_id}
            if name:
                updates["name"] = name
            return await self.parent_repo.update_parent(db, stub, updates)

        # 3. Brand-new parent
        parent = ParentSchema(user_id=user_id, phone_number=phone, name=name)
        return await self.parent_repo.create_parent(db, parent)
```

- [ ] **Step 4: Run them, verify they pass**

Run: `uv run pytest tests/test_parent_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix services/ tests/
git add services/parent_service.py tests/test_parent_service.py
git commit -m "fix: claim parent stub by phone on OTP + persist parent name (#36)"
```

---

### Task 5: Notification dispatch orchestrator (gate + audit)

**Files:**
- Modify: `services/notification_service.py`
- Test: `tests/test_notification_dispatch.py`

**Interfaces:**
- Consumes: `send_template_message` (patched in tests), `NotificationRepository`, `ParentSchema`.
- Produces:
  `async def dispatch(db, *, parent, student_id, institute_id, type, template_name, components, join_url=None, force=False) -> NotificationSchema`
  where `parent: ParentSchema`, `type: NotificationType`, `template_name: str`, `components: list[dict]`, `join_url: str | None`.
  Rules: parent-facing reminder types are `FEE_REMINDER` and `ABSENCE`. `ENROLLMENT_INVITE` and `FEE_RECEIPT` are always attempted regardless of verification.

- [ ] **Step 1: Write the failing tests**

`tests/test_notification_dispatch.py`:
```python
import uuid

import pytest

from models.notification_base import NotificationStatus, NotificationType
from models.parent_base import ParentSchema
from repositories.parent_repository import ParentRepository
from services import notification_service


@pytest.fixture
def fake_send(monkeypatch):
    calls = []

    async def _send(to, template_name, components=None, language="en"):
        calls.append({"to": to, "template_name": template_name, "components": components})
        return {"messages": [{"id": "wamid.TEST"}]}

    monkeypatch.setattr(notification_service, "send_template_message", _send)
    return calls


@pytest.mark.asyncio
async def test_verified_parent_sends_and_logs_sent(db_session, fake_send):
    repo = ParentRepository()
    parent = ParentSchema(phone_number="9876543210", name="A", user_id=uuid.uuid4())
    await repo.create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=1, institute_id=7,
        type=NotificationType.FEE_REMINDER, template_name="fee_reminder",
        components=[{"type": "body"}],
    )
    assert log.status == NotificationStatus.SENT
    assert fake_send[-1]["template_name"] == "fee_reminder"
    assert log.meta_data["whatsapp_response"] == {"messages": [{"id": "wamid.TEST"}]}
    assert log.meta_data["institute_id"] == 7


@pytest.mark.asyncio
async def test_unverified_reminder_sends_invite_and_logs_skipped(db_session, fake_send):
    repo = ParentRepository()
    parent = ParentSchema(phone_number="9000000000", name="B", user_id=None)
    await repo.create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=2, institute_id=7,
        type=NotificationType.FEE_REMINDER, template_name="fee_reminder",
        components=[{"type": "body"}], join_url="https://batchbook.in/join/ABC123",
    )
    assert log.status == NotificationStatus.SKIPPED_UNVERIFIED
    assert log.reason == "parent number not verified"
    assert fake_send[-1]["template_name"] == "enrollment_invite"  # invite sent instead


@pytest.mark.asyncio
async def test_send_failure_logs_failed(db_session, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(notification_service, "send_template_message", _boom)
    repo = ParentRepository()
    parent = ParentSchema(phone_number="9222222222", name="C", user_id=uuid.uuid4())
    await repo.create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=3, institute_id=7,
        type=NotificationType.FEE_RECEIPT, template_name="fee_receipt",
        components=[{"type": "body"}],
    )
    assert log.status == NotificationStatus.FAILED
    assert "api down" in (log.reason or "")
```

- [ ] **Step 2: Run them, verify they fail**

Run: `uv run pytest tests/test_notification_dispatch.py -v`
Expected: FAIL — `AttributeError: module 'services.notification_service' has no attribute 'dispatch'`

- [ ] **Step 3: Implement dispatch**

Add to the top of `services/notification_service.py` (after existing imports):
```python
from sqlalchemy.ext.asyncio import AsyncSession

from models.notification_base import (
    NotificationSchema,
    NotificationStatus,
    NotificationType,
)
from repositories.notification_repository import NotificationRepository

_REMINDER_TYPES = {NotificationType.FEE_REMINDER, NotificationType.ABSENCE}
```

Then add this function:
```python
async def dispatch(
    db: AsyncSession,
    *,
    parent,
    student_id: int | None,
    institute_id: int | None,
    type: NotificationType,
    template_name: str,
    components: list[dict],
    join_url: str | None = None,
    force: bool = False,
) -> NotificationSchema:
    """Send a WhatsApp template (verification-gated) and audit the result.

    - Verified parent (``parent.user_id`` set) or non-reminder type → send ``template_name``.
    - Unverified parent + reminder type → send ``enrollment_invite`` link instead and log
      status ``skipped_unverified``.
    - Every outcome (sent / skipped / failed) is persisted to the Notification table with the
      message components, institute_id, and the raw WhatsApp API response in ``meta_data``.
    """
    repo = NotificationRepository()
    verified = parent is not None and parent.user_id is not None
    is_reminder = type in _REMINDER_TYPES

    if not verified and is_reminder and not force:
        # Re-invite instead of reminding an unverified number
        invite_components = (
            _body("Student", "your institute", join_url) if join_url else components
        )
        status = NotificationStatus.SKIPPED_UNVERIFIED
        reason = "parent number not verified"
        sent_template = "enrollment_invite"
        sent_components = invite_components
    else:
        status = NotificationStatus.SENT
        reason = None
        sent_template = template_name
        sent_components = components

    whatsapp_response = None
    try:
        whatsapp_response = await send_template_message(
            to=_to(parent.phone_number),
            template_name=sent_template,
            components=sent_components,
        )
    except Exception as exc:
        status = NotificationStatus.FAILED
        reason = str(exc)
        logger.error(f"[WhatsApp] dispatch {sent_template} failed: {exc}")

    notification = NotificationSchema(
        parent_id=getattr(parent, "id", None),
        student_id=student_id,
        institute_id=institute_id,
        type=type,
        status=status,
        reason=reason,
        meta_data={
            "message": {"template": sent_template, "components": sent_components},
            "institute_id": institute_id,
            "whatsapp_response": whatsapp_response,
        },
    )
    return await repo.create(db, notification)
```

- [ ] **Step 4: Run them, verify they pass**

Run: `uv run pytest tests/test_notification_dispatch.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
uv run ruff check --fix services/ tests/
git add services/notification_service.py tests/test_notification_dispatch.py
git commit -m "feat: verification-gated, audited notification dispatch"
```

---

### Task 6: Route fee reminders + receipt + invite through dispatch

**Files:**
- Modify: `routes/fee_route.py` (`send_fee_reminder_for_record`, `send_fee_reminders_for_all`, payment-receipt send in `mark_payment`)
- Modify: `routes/enrollment_route.py` (`invite_student` — log the invite + include student name in join URL)
- Test: `tests/test_fee_routes.py` (add one reminder-audit test) — or create `tests/test_notification_audit_routes.py`

**Interfaces:**
- Consumes: `notification_service.dispatch`, `NotificationType`, `_body` (existing in notification_service).
- Background tasks open their own session via `AsyncSessionLocal` from `db.session`.

- [ ] **Step 1: Add a background helper in notification_service**

Add to `services/notification_service.py`:
```python
async def dispatch_in_background(**kwargs) -> None:
    """Background-task wrapper: opens its own DB session and dispatches.

    Pass the same keyword args as ``dispatch`` minus ``db``.
    """
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await dispatch(db, **kwargs)
        except Exception as exc:  # never let a background failure escape
            logger.error(f"[WhatsApp] background dispatch failed: {exc}")
```

- [ ] **Step 2: Rewire the single fee reminder**

In `routes/fee_route.py` `send_fee_reminder_for_record`, replace the `background_tasks.add_task(send_fee_reminder, ...)` block with building the join URL + reminder components and dispatching:
```python
    from services.notification_service import _body, dispatch_in_background
    from models.notification_base import NotificationType

    inst = await institute_service.institute_repo.get_by_id(db, institute_id)
    join_url = f"https://batchbook.in/join/{inst.join_code}" if inst else None
    link_text = fee_record.payment_link or "Contact your institute"
    amount_str = (
        f"{int(amount_pending):,}" if amount_pending == int(amount_pending)
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
```
(Remove the now-unused `from services.notification_service import send_fee_reminder` import in this function.)

- [ ] **Step 3: Rewire remind-all the same way**

In `send_fee_reminders_for_all`, inside the loop, replace the `background_tasks.add_task(send_fee_reminder, ...)` with the same `dispatch_in_background(... type=NotificationType.FEE_REMINDER ...)` pattern (build `components` via `_body`, resolve `join_url` once before the loop from the institute's join_code).

- [ ] **Step 4: Include student name in the invite URL**

In `routes/enrollment_route.py` `invite_student`, change:
```python
    join_url = f"{base_url}/join/{join_code}"
```
to:
```python
    from urllib.parse import quote
    join_url = f"{base_url}/join/{join_code}?student={quote(request.student_name)}"
```
Leave the existing `send_enrollment_invite(...)` call as-is (it already audits via Task 5 only if routed through dispatch — optional: wrap it with `dispatch_in_background type=ENROLLMENT_INVITE` for audit symmetry; do so if time permits).

- [ ] **Step 5: Write an audit test**

`tests/test_notification_audit_routes.py` — exercise `send_fee_reminder_for_record` against an unverified parent and assert a `Notification` row with `SKIPPED_UNVERIFIED` is written. (Use the existing fee-route test fixtures in `tests/` as a template for auth + seeding; monkeypatch `services.notification_service.send_template_message` to a fake returning `{"messages": [{"id": "x"}]}`. Because the route uses BackgroundTasks, call the dispatch path synchronously in the test by asserting on a direct `dispatch_in_background(...)` call with a seeded unverified parent rather than the full HTTP round-trip.)

```python
import uuid
import pytest
from models.parent_base import ParentSchema
from models.notification_base import NotificationStatus, NotificationType
from repositories.parent_repository import ParentRepository
from repositories.notification_repository import NotificationRepository
from services import notification_service


@pytest.mark.asyncio
async def test_unverified_fee_reminder_audited_as_skipped(db_session, monkeypatch):
    async def _send(to, template_name, components=None, language="en"):
        return {"messages": [{"id": "wamid.X"}]}
    monkeypatch.setattr(notification_service, "send_template_message", _send)

    parent = ParentSchema(phone_number="9333333333", name="P", user_id=None)
    await ParentRepository().create_parent(db_session, parent)

    log = await notification_service.dispatch(
        db_session, parent=parent, student_id=5, institute_id=2,
        type=NotificationType.FEE_REMINDER, template_name="fee_reminder",
        components=[{"type": "body"}], join_url="https://batchbook.in/join/CODE",
    )
    assert log.status == NotificationStatus.SKIPPED_UNVERIFIED

    latest = await NotificationRepository().get_latest_by_student_ids(db_session, [5])
    assert latest[5].status == NotificationStatus.SKIPPED_UNVERIFIED
```

- [ ] **Step 6: Run the suite**

Run: `uv run pytest tests/test_notification_audit_routes.py tests/test_notification_dispatch.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
uv run ruff check --fix routes/ services/ tests/
git add routes/fee_route.py routes/enrollment_route.py services/notification_service.py tests/test_notification_audit_routes.py
git commit -m "feat: route fee reminders + invite through audited dispatch"
```

---

### Task 7: Surface verification + last-notification status in fee dashboard

**Files:**
- Modify: `routes/responses/fee_dashboard_response.py`
- Modify: `routes/fee_route.py` (the dashboard endpoint that builds `FeeDashboardResponse`)
- Test: `tests/test_fee_dashboard_status.py`

**Interfaces:**
- Consumes: `NotificationRepository.get_latest_by_student_ids`, parent verification.
- Produces: `FeeRecordSummary` gains `parent_is_verified: bool` and `last_notification_status: str | None` and `last_notification_reason: str | None`.

- [ ] **Step 1: Extend the response model**

In `routes/responses/fee_dashboard_response.py`, add to `FeeRecordSummary`:
```python
    parent_is_verified: bool = True
    last_notification_status: str | None = None
    last_notification_reason: str | None = None
```

- [ ] **Step 2: Populate in the dashboard endpoint**

Find the dashboard handler in `routes/fee_route.py` that constructs `FeeRecordSummary` items. After the records query, fetch latest notifications for the student ids and the parents' verification, then set the three new fields per record. Sketch:
```python
    from repositories.notification_repository import NotificationRepository
    student_ids = [r.student_id for r in rows]  # adapt to actual row shape
    latest = await NotificationRepository().get_latest_by_student_ids(db, student_ids)
    # when building each FeeRecordSummary:
    #   parent_is_verified = parent.user_id is not None
    #   note = latest.get(student_id)
    #   last_notification_status = note.status.value if note else None
    #   last_notification_reason = note.reason if note else None
```
(Adapt variable names to the existing query in that handler — the join already includes student/parent in the reminder handlers; mirror that join here if the dashboard query lacks parent.)

- [ ] **Step 3: Write the test**

`tests/test_fee_dashboard_status.py`: seed an unverified parent + student + a fee record + a `SKIPPED_UNVERIFIED` Notification, call the dashboard endpoint via the async test client, assert the matching record has `parent_is_verified is False` and `last_notification_status == "SKIPPED_UNVERIFIED"`. (Use the existing fee dashboard test as the fixture template.)

- [ ] **Step 4: Run it**

Run: `uv run pytest tests/test_fee_dashboard_status.py -v`
Expected: PASS

- [ ] **Step 5: Full backend suite + commit**

Run: `uv run pytest`
Expected: all green.
```bash
uv run ruff check --fix routes/ tests/
git add routes/responses/fee_dashboard_response.py routes/fee_route.py tests/test_fee_dashboard_status.py
git commit -m "feat: expose parent verification + last notification status on fee dashboard"
```

---

## PART B — FRONTEND (batchbookui submodule)

> Run all frontend commands from `batchbookui/`. Create branch first:
> `cd batchbookui && git checkout -b feat/student-onboarding-ui`

### Task 8: ownerService.inviteStudent

**Files:**
- Modify: `batchbookui/src/services/ownerService.js`
- Test: `batchbookui/src/test/ownerService.test.js`

**Interfaces:**
- Produces: `inviteStudent({ student_name, parent_name, parent_phone, batch_id, due_day, first_month_amount }) -> Promise<EnrollmentResponse>` calling `POST /enrollment/invite`.

- [ ] **Step 1: Write the failing test**

Add to `batchbookui/src/test/ownerService.test.js` (follow the existing mock-axios pattern in that file):
```js
import { inviteStudent } from '../services/ownerService';
// ...
it('inviteStudent posts to /enrollment/invite with parent fields', async () => {
  api.post.mockResolvedValueOnce({ data: { id: 1 } });
  await inviteStudent({
    student_name: 'Rahul', parent_name: 'Asha', parent_phone: '9876543210',
    batch_id: 3, due_day: 5,
  });
  expect(api.post).toHaveBeenCalledWith('/enrollment/invite', expect.objectContaining({
    student_name: 'Rahul', parent_name: 'Asha', parent_phone: '9876543210', batch_id: 3,
  }));
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd batchbookui && npm run test -- ownerService`
Expected: FAIL — `inviteStudent is not a function`

- [ ] **Step 3: Implement**

In `batchbookui/src/services/ownerService.js`:
```js
/**
 * Owner invites a new student: backend creates Parent + Student + Enrollment and
 * sends the enrollment_invite WhatsApp link. Replaces addStudentAndEnroll.
 */
export async function inviteStudent({
  student_name, parent_name, parent_phone, batch_id, due_day, first_month_amount,
}) {
  const { data } = await api.post('/enrollment/invite', {
    student_name, parent_name, parent_phone, batch_id, due_day, first_month_amount,
  });
  return data;
}
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd batchbookui && npm run test -- ownerService`
Expected: PASS

- [ ] **Step 5: Commit (inside submodule)**

```bash
cd batchbookui
git add src/services/ownerService.js src/test/ownerService.test.js
git commit -m "feat: add inviteStudent service calling /enrollment/invite"
```

---

### Task 9: AddStudentModal — parent name + invite endpoint

**Files:**
- Modify: `batchbookui/src/pages/owner/AddStudentModal.jsx`
- Test: `batchbookui/src/test/AddStudentModal.test.jsx`

**Interfaces:**
- Consumes: `inviteStudent` from Task 8.

- [ ] **Step 1: Update the test**

In `batchbookui/src/test/AddStudentModal.test.jsx`, mock `inviteStudent` and assert that submitting the form (student name + parent name + parent phone + batch) calls `inviteStudent` with `parent_name` and `parent_phone`. Add an assertion that a "Parent Name" field is rendered (`getByLabelText(/parent name/i)`).

- [ ] **Step 2: Run it, verify it fails**

Run: `cd batchbookui && npm run test -- AddStudentModal`
Expected: FAIL — no Parent Name field / `inviteStudent` not called.

- [ ] **Step 3: Implement the modal changes**

In `AddStudentModal.jsx`:
1. Replace the import `import { addStudentAndEnroll } from '../../services/ownerService';` with `import { inviteStudent } from '../../services/ownerService';`.
2. Add `parent_name: ''` to the initial `form` state and to the `handleClose` reset object.
3. Add a "Parent Name" required field (mirror the existing Student Name `<Grid item xs={12}>` TextField, `value={form.parent_name}`, `onChange={handleChange('parent_name')}`, `error/helperText={errors.parent_name}`, `data-testid="parent-name-input"`).
4. Relabel the phone field `label="Parent's phone"`.
5. In `validate`, add: `if (!form.parent_name.trim()) errors.parent_name = 'Parent name is required.';`
6. Replace the `addStudentAndEnroll({...})` call in `handleSubmit` with:
```js
      await inviteStudent({
        student_name: form.name.trim(),
        parent_name: form.parent_name.trim(),
        parent_phone: form.phone_number.trim(),
        batch_id: Number(form.batch_id),
        due_day: Number(form.due_day),
        first_month_amount:
          form.first_month_amount !== '' ? Number(form.first_month_amount) : undefined,
      });
```
(Drop the `email` field from the payload — `/enrollment/invite` does not accept it. Leave the email input in the form only if other tests rely on it; otherwise remove it.)

- [ ] **Step 4: Run it, verify it passes**

Run: `cd batchbookui && npm run test -- AddStudentModal`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd batchbookui
git add src/pages/owner/AddStudentModal.jsx src/test/AddStudentModal.test.jsx
git commit -m "feat: collect parent name + use invite endpoint in AddStudentModal (#34)"
```

---

### Task 10: Invite-link landing route `/join/:joinCode`

**Files:**
- Create: `batchbookui/src/components/onboarding/JoinInstitute.jsx`
- Modify: `batchbookui/src/App.jsx` (add route)

**Interfaces:**
- Reuses: `PhoneOtpStep` (existing), `/parent/verify_otp`, `/parent/join-institute`.

- [ ] **Step 1: Create the landing component**

`batchbookui/src/components/onboarding/JoinInstitute.jsx`:
```jsx
import React from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { Box, Card, Typography } from '@mui/material';
import PhoneOtpStep from './PhoneOtpStep';

export default function JoinInstitute() {
  const { joinCode } = useParams();
  const [params] = useSearchParams();
  const studentName = params.get('student') || '';
  const navigate = useNavigate();

  const handleSuccess = async () => {
    // Parent claimed their stub on OTP verify (backend links by phone).
    // Persist join code for the join-institute call if the parent is new.
    try {
      localStorage.setItem('bb_join_code', joinCode || '');
    } catch { /* ignore */ }
    navigate('/dashboard/student');
  };

  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', bgcolor: 'background.default', p: 2 }}>
      <Card sx={{ width: '100%', maxWidth: 460, p: 4, borderRadius: 4, bgcolor: 'background.paper' }}>
        <Typography variant="h6" fontWeight={700} gutterBottom>
          {studentName ? `Welcome, ${studentName}'s parent!` : 'Verify your number'}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Verify your phone to view attendance, fees & schedule.
        </Typography>
        <PhoneOtpStep label="Your phone number" onSuccess={handleSuccess} />
      </Card>
    </Box>
  );
}
```

- [ ] **Step 2: Register the route**

In `batchbookui/src/App.jsx`, import `JoinInstitute` and add inside `<Routes>`:
```jsx
            <Route path="/join/:joinCode" element={<JoinInstitute />} />
```

- [ ] **Step 3: Smoke-test the build**

Run: `cd batchbookui && npm run build`
Expected: build succeeds (no missing-import errors).

- [ ] **Step 4: Commit**

```bash
cd batchbookui
git add src/components/onboarding/JoinInstitute.jsx src/App.jsx
git commit -m "feat: add /join/:joinCode invite-link landing route (#34)"
```

---

### Task 11: Self-onboarding passes parent name + dashboard badge

**Files:**
- Modify: `batchbookui/src/components/onboarding/PhoneOtpStep.jsx`
- Modify: `batchbookui/src/pages/owner/StudentsPage.jsx` (or `FeesPage.jsx` — wherever per-student status renders)

**Interfaces:**
- Consumes: `last_notification_status` / `parent_is_verified` from Task 7's dashboard response.

- [ ] **Step 1: Pass parent name in verify_otp**

`PhoneOtpStep` currently sends `{ phone, token }`. Make it accept an optional `name` prop and include it when present:
```jsx
export default function PhoneOtpStep({ phone: initialPhone = '', label = 'Phone number', name, onSuccess }) {
```
In `verifyOtp`, change the body to:
```js
        body: JSON.stringify(name ? { phone, token: otp, name } : { phone, token: otp }),
```
And in `OnboardingWizard.jsx`, pass the collected parent name to the parent OTP step:
```jsx
      case 'parentOtp':
        return <PhoneOtpStep phone={data.parentPhone} name={data.parentName} label="Parent's phone" onSuccess={handleOtpSuccess}/>;
```

- [ ] **Step 2: Render the unverified badge**

In the owner students/fees list, where each student/fee row renders, add a small warning chip when `record.parent_is_verified === false` or `record.last_notification_status === 'SKIPPED_UNVERIFIED'`:
```jsx
{record.parent_is_verified === false && (
  <Chip size="small" color="warning" label="Parent not verified — invite re-sent" />
)}
```
(Import `Chip` from `@mui/material`. Adapt `record` to the actual prop name in that component.)

- [ ] **Step 3: Build + test**

Run: `cd batchbookui && npm run build && npm run test`
Expected: build + tests pass.

- [ ] **Step 4: Commit**

```bash
cd batchbookui
git add src/components/onboarding/PhoneOtpStep.jsx src/components/onboarding/OnboardingWizard.jsx src/pages/owner/StudentsPage.jsx
git commit -m "feat: persist parent name on self-onboard + show unverified badge (#36)"
```

---

### Task 12: Push submodule + bump pointer + open PRs

**Files:**
- Modify: `BatchBook` submodule pointer.

- [ ] **Step 1: Push the frontend branch**

```bash
cd batchbookui
git push -u origin feat/student-onboarding-ui
```

- [ ] **Step 2: Bump the pointer in the parent repo**

```bash
cd ..
git add batchbookui   # NO trailing slash — stages the new SHA pointer
git commit -m "chore: bump batchbookui submodule — student onboarding UI"
```

- [ ] **Step 3: Push backend branch**

```bash
git push -u origin feat/student-onboarding-notification-audit
```

- [ ] **Step 4: Open the two PRs**

```bash
gh pr create --repo bedantsharma/batchbookui --head feat/student-onboarding-ui \
  --title "Student onboarding: parent name + invite endpoint + join landing (#34)" \
  --body "Closes #34. See BatchBook spec."
gh pr create --repo bedantsharma/BatchBook --head feat/student-onboarding-notification-audit \
  --title "End-to-end student onboarding + audited notifications (#38, #36)" \
  --body "Closes #38, #36. Routes add-student through /enrollment/invite, claims parent stub by phone on OTP, adds Notification audit table with verification-gated reminders."
```

---

## Self-Review notes
- Spec §4.1 → Task 4. §4.2 → Tasks 1–3. §4.3 → Task 5. §4.4 → Task 6. §4.5 → Task 7.
  §5.1 → Task 9. §5.2 → Task 8. §5.3 → Task 10. §5.4/§5.5 → Task 11. §6 tests folded into each task.
- Migration runs against the prod Postgres separately (`uv run alembic upgrade head`) — note for deploy, not a task step.
