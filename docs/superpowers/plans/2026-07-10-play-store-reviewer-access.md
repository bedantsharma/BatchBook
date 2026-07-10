# Play Store Reviewer Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Google Play reviewers a working Owner login (`9999999999`) and Student login (`9999999998`) inside `BATCHBOOK_APP`, both pre-populated with realistic data, using Supabase's already-configured Test OTP feature — no auth code changes.

**Architecture:** A new idempotent backend admin endpoint (`POST /admin/seed-demo-accounts`) seeds an Owner→Institute→Batches→Parent→Student→Enrollments→Sessions→Attendance→FeeRecords graph by calling the same production service methods real signups use (`EnrollmentService.invite_student`, `BatchService.create_batch`, `FeeService.setup_fee_structure`/`generate_monthly_records`, `AttendanceService.create_session`/`bulk_mark`). Two new React Native screens fill the currently-missing student OTP login path in `BATCHBOOK_APP`, mirroring the existing owner screens exactly.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), React Native + Expo Router + TypeScript (mobile).

**Spec:** `docs/superpowers/specs/2026-07-10-play-store-reviewer-access-design.md`

## Global Constraints

- **Backend package manager:** `uv` — use `uv add <pkg>` / `uv run <cmd>`, never bare `pip`/`python`.
- **Backend linter:** `ruff`, line length 100, Python 3.14 target, auto-fix on.
- **Backend test runner:** `pytest`, async mode `auto`. Run via `uv run pytest`.
- **Mobile repo:** `BATCHBOOK_APP` is a **sibling directory** to `BatchBook` (`/Users/bedantsharma/PycharmProjects/BATCHBOOK_APP`), a separate git repo — not a submodule. Commit there independently.
- **Mobile has no automated test framework** (no jest configured) — verification is `npx tsc --noEmit`, `npm run lint` (= `expo lint`), plus a manual QA pass.
- **Reviewer identities (already configured in Supabase, do not change):** Owner phone `9999999999`, Student/Parent phone `9999999998`, OTP `110304` for both, valid through 2026-08-31.
- **No changes anywhere to `services/auth_service.py`, JWT validation, or Supabase auth configuration.**
- **Every seed operation must be idempotent** — safe to call `POST /admin/seed-demo-accounts` any number of times without creating duplicate rows or crashing.
- **Coordination protocol (applies to every task below):** this plan is executed by a fresh subagent per task. Every task's final step is writing a status file to `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/<task-slug>.md` (outside both git repos — never committed) documenting what was done, what wasn't, and exact file paths/line numbers touched, then updating the shared `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/knowledge_base.md` index. This lets later tasks' subagents (and a final reviewing agent) understand prior work without re-deriving it. Exact template given in Task 1, Step 1.

---

## Task 1: `DemoSeedService` — Owner, Institute, Batches (idempotent)

**Files:**
- Create: `services/demo_seed_service.py`
- Test: `tests/test_demo_seed_service.py`

**Interfaces:**
- Consumes: `OwnerRepository` (`repositories/owner_repository.py`: `get_by_phone`, `create_owner`), `InstituteRepository` (`repositories/institute_repository.py`: `get_by_owner_id`, `create`), `BatchService.create_batch`/`list_batches` (`services/batch_service.py`), `FeeService.setup_fee_structure` (`services/fee_service.py`).
- Produces: `DemoSeedService` class with `OWNER_PHONE = "9999999999"` and `STUDENT_PARENT_PHONE = "9999999998"` module-level constants; `DemoSeedResult` dataclass with fields `owner_created: bool`, `institute_created: bool`, `batches_created: list[str]`; a `seed(db: AsyncSession) -> DemoSeedResult` method (partial in this task — Task 2 extends it). Task 3 depends on `DemoSeedService`, `DemoSeedResult`, `get_demo_seed_service()`.

- [ ] **Step 1: Create the scratchpad coordination folder and this task's status file (write this LAST, after Steps 2-6, but create the folder now)**

```bash
mkdir -p /Users/bedantsharma/PycharmProjects/scratchPadForSubAgents
```

Do not write the `.md` files yet — come back to this after Step 6 passes. When you do, create
`/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/backend-task-1-owner-institute-batches.md`:

```markdown
# backend-task-1-owner-institute-batches

## Done
- Created `services/demo_seed_service.py`: `DemoSeedService` with `_seed_owner`, `_seed_institute`,
  `_seed_batches` methods and a partial `seed()` orchestrator (owner+institute+batches only —
  Task 2 extends this with parent/student/sessions/attendance/fees).
- `OWNER_PHONE = "9999999999"`, `STUDENT_PARENT_PHONE = "9999999998"` module constants defined here
  (Task 2 and the route reuse these).
- Idempotency: re-running `seed()` does not duplicate the Owner/Institute/Batch rows — verified by
  `tests/test_demo_seed_service.py::test_seed_is_idempotent_on_second_call`.
- [Fill in: did all tests pass? paste the pytest summary line.]

## Not done / left for Task 2
- Parent/Student/Enrollment/ClassSession/Attendance/FeeRecord seeding — `DemoSeedResult` currently
  only has `owner_created`, `institute_created`, `batches_created` fields.
- No HTTP route yet — `DemoSeedService` is not wired into `routes/admin_route.py` (Task 3).

## Where to find it
- `services/demo_seed_service.py` — new file, full contents as of this task.
- `tests/test_demo_seed_service.py` — new file.
- [Fill in: note any deviation from the plan and why, if you had to make a judgment call.]
```

Then append a row to `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/knowledge_base.md`
(create it with this header if it doesn't exist yet):

```markdown
# Subagent Knowledge Base — Play Store Reviewer Access

| Task file | Summary |
|---|---|
| backend-task-1-owner-institute-batches.md | Seeds Owner+Institute+2 Batches (idempotent), no HTTP route yet |
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_demo_seed_service.py
"""Integration tests for DemoSeedService — seeds the Play Store reviewer accounts."""

from services.demo_seed_service import (
    OWNER_PHONE,
    DemoSeedService,
)
from repositories.owner_repository import OwnerRepository
from repositories.institute_repository import InstituteRepository
from services.batch_service import BatchService


async def test_seed_creates_owner_institute_and_batches(db_session):
    service = DemoSeedService()

    result = await service.seed(db_session)

    assert result.owner_created is True
    assert result.institute_created is True
    assert sorted(result.batches_created) == ["Class 10 Maths", "Class 12 Physics"]

    owner = await OwnerRepository().get_by_phone(db_session, OWNER_PHONE)
    assert owner is not None
    assert owner.name == "Demo Owner"

    institute = await InstituteRepository().get_by_owner_id(db_session, owner.id)
    assert institute is not None
    assert institute.name == "BatchBook Demo Academy"

    batches = await BatchService().list_batches(db_session, institute.id)
    assert {b.name for b in batches} == {"Class 10 Maths", "Class 12 Physics"}
    for batch in batches:
        assert batch.days_of_week  # schedule set
        assert batch.max_capacity > 0


async def test_seed_is_idempotent_on_second_call(db_session):
    service = DemoSeedService()
    await service.seed(db_session)

    result = await service.seed(db_session)

    assert result.owner_created is False
    assert result.institute_created is False
    assert result.batches_created == []

    owner = await OwnerRepository().get_by_phone(db_session, OWNER_PHONE)
    institute = await InstituteRepository().get_by_owner_id(db_session, owner.id)
    batches = await BatchService().list_batches(db_session, institute.id)
    assert len(batches) == 2  # not 4 — no duplicates
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_demo_seed_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.demo_seed_service'`

- [ ] **Step 4: Write the implementation**

```python
# services/demo_seed_service.py
import secrets
import string
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from models.batch_base import BatchSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from services.batch_service import BatchService
from services.fee_service import FeeService

OWNER_PHONE = "9999999999"
STUDENT_PARENT_PHONE = "9999999998"

_BATCH_SPECS = [
    {
        "name": "Class 10 Maths",
        "subject": "Maths",
        "grade": "10",
        "start_time": time(16, 0),
        "end_time": time(17, 0),
        "days_of_week": ["MON", "WED", "FRI"],
        "max_capacity": 30,
        "end_date": date(2027, 3, 31),
        "monthly_amount": Decimal("1500.00"),
    },
    {
        "name": "Class 12 Physics",
        "subject": "Physics",
        "grade": "12",
        "start_time": time(17, 30),
        "end_time": time(18, 30),
        "days_of_week": ["TUE", "THU", "SAT"],
        "max_capacity": 25,
        "end_date": date(2027, 3, 31),
        "monthly_amount": Decimal("1800.00"),
    },
]


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass
class DemoSeedResult:
    owner_created: bool
    institute_created: bool
    batches_created: list[str] = field(default_factory=list)


class DemoSeedService:
    """Seeds the two Play Store reviewer accounts with realistic demo data.

    Every method is idempotent — safe to call `seed()` any number of times.
    Mirrors production creation paths (BatchService, FeeService, and in
    demo_seed_service Task 2, EnrollmentService.invite_student) rather than
    inserting rows directly, so the seeded data has the same shape real
    signups produce.
    """

    def __init__(self) -> None:
        self.owner_repo = OwnerRepository()
        self.institute_repo = InstituteRepository()
        self.batch_service = BatchService()
        self.fee_service = FeeService()

    async def _seed_owner(self, db: AsyncSession) -> tuple[OwnerSchema, bool]:
        owner = await self.owner_repo.get_by_phone(db, OWNER_PHONE)
        if owner:
            return owner, False
        owner = OwnerSchema(
            name="Demo Owner",
            phone_number=OWNER_PHONE,
            teacher_id=uuid4(),
            institute_name="BatchBook Demo Academy",
            city="Gurugram",
        )
        owner = await self.owner_repo.create_owner(db, owner)
        return owner, True

    async def _seed_institute(
        self, db: AsyncSession, owner: OwnerSchema
    ) -> tuple[InstituteSchema, bool]:
        institute = await self.institute_repo.get_by_owner_id(db, owner.id)
        if institute:
            return institute, False
        institute = InstituteSchema(
            owner_id=owner.id,
            name="BatchBook Demo Academy",
            city="Gurugram",
            join_code=_generate_join_code(),
        )
        institute = await self.institute_repo.create(db, institute)
        return institute, True

    async def _seed_batches(
        self, db: AsyncSession, institute: InstituteSchema
    ) -> tuple[list[BatchSchema], list[str]]:
        existing = await self.batch_service.list_batches(db, institute.id)
        by_name = {b.name: b for b in existing}

        batches: list[BatchSchema] = []
        created_names: list[str] = []
        for spec in _BATCH_SPECS:
            spec = dict(spec)
            monthly_amount = spec.pop("monthly_amount")
            batch = by_name.get(spec["name"])
            if batch is None:
                batch = await self.batch_service.create_batch(db, institute_id=institute.id, **spec)
                created_names.append(batch.name)
            await self.fee_service.setup_fee_structure(db, batch.id, monthly_amount)
            batches.append(batch)
        return batches, created_names

    async def seed(self, db: AsyncSession) -> DemoSeedResult:
        owner, owner_created = await self._seed_owner(db)
        institute, institute_created = await self._seed_institute(db, owner)
        _batches, batches_created = await self._seed_batches(db, institute)

        return DemoSeedResult(
            owner_created=owner_created,
            institute_created=institute_created,
            batches_created=batches_created,
        )


def get_demo_seed_service() -> DemoSeedService:
    return DemoSeedService()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_demo_seed_service.py -v`
Expected: PASS (2 tests)

Also run the full suite to confirm nothing else broke:
Run: `uv run pytest -v`
Expected: all tests pass (261+ existing + 2 new)

- [ ] **Step 6: Lint**

Run: `uv run ruff check services/demo_seed_service.py tests/test_demo_seed_service.py`
Expected: no errors (auto-fix on; if it reformats, re-run tests)

- [ ] **Step 7: Write the scratchpad status file and knowledge_base.md entry (see Step 1 template above), then commit**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
git add services/demo_seed_service.py tests/test_demo_seed_service.py
git commit -m "$(cat <<'EOF'
feat: seed demo Owner+Institute+Batches for Play Store reviewer account

First half of DemoSeedService — idempotent seeding for the reviewer-facing
owner account (9999999999). Reuses BatchService/FeeService so seeded batches
have the same shape as real ones.
EOF
)"
```

---

## Task 2: `DemoSeedService` — Parent, Student, Enrollments, Sessions, Attendance, Fee Records

**Files:**
- Modify: `services/demo_seed_service.py` (extends Task 1's file)
- Modify: `tests/test_demo_seed_service.py` (extends Task 1's tests)

**Interfaces:**
- Consumes: `DemoSeedService`, `DemoSeedResult`, `OWNER_PHONE`, `STUDENT_PARENT_PHONE` from Task 1 (`services/demo_seed_service.py`). `EnrollmentService.invite_student`/`enroll_student`/`enrollment_repo.get_by_student_and_batch` (`services/enrollment_service.py`). `ParentRepository.get_by_phone`/`get_students_by_parent_id` (`repositories/parent_repository.py`). `StudentRepository.get_by_id` (`repositories/student_repository.py`). `AttendanceService.create_session`/`bulk_mark` (`services/attendance_service.py`). `FeeService.generate_monthly_records`/`mark_payment`/`fee_repo.get_record_by_enrollment_and_month` (`services/fee_service.py`). `FeeStatus` enum (`models/fee_record_base.py`).
- Produces: `DemoSeedResult` extended with `student_created: bool`, `sessions_created: int`, `fee_records_created: int`. `seed()` now returns the full result. Task 3 (the route) consumes this final `DemoSeedResult` shape.

- [ ] **Step 1: Write the failing test — append to `tests/test_demo_seed_service.py`**

```python
# Add these imports to the top of tests/test_demo_seed_service.py, alongside the existing ones:
from datetime import date, timedelta

from models.fee_record_base import FeeStatus
from repositories.parent_repository import ParentRepository
from services.demo_seed_service import STUDENT_PARENT_PHONE


# Add these tests to the end of the file:

async def test_seed_creates_parent_student_and_full_demo_data(db_session):
    service = DemoSeedService()

    result = await service.seed(db_session)

    assert result.student_created is True
    assert result.sessions_created == 6  # 3 sessions x 2 batches
    assert result.fee_records_created == 4  # 2 months x 2 batches

    parent = await ParentRepository().get_by_phone(db_session, STUDENT_PARENT_PHONE)
    assert parent is not None
    assert parent.name == "Rina Sharma"
    assert parent.institute_id is not None
    assert parent.user_id is None  # owner-invited stub shape, not yet OTP-verified

    children = await ParentRepository().get_students_by_parent_id(db_session, parent.id)
    assert len(children) == 1
    assert children[0].name == "Aarav Sharma"
    assert children[0].institute_id == parent.institute_id

    from repositories.enrollment_repository import EnrollmentRepository
    from services.batch_service import BatchService

    institute_id = parent.institute_id
    batches = await BatchService().list_batches(db_session, institute_id)
    assert len(batches) == 2
    for batch in batches:
        enrollment = await EnrollmentRepository().get_by_student_and_batch(
            db_session, children[0].id, batch.id
        )
        assert enrollment is not None
        assert enrollment.is_active is True

        last_month_record = await FeeService().fee_repo.get_record_by_enrollment_and_month(
            db_session,
            enrollment.id,
            (date.today().replace(day=1) - timedelta(days=1)).replace(day=1),
        )
        assert last_month_record is not None
        assert last_month_record.status == FeeStatus.FULLY_PAID


async def test_seed_is_fully_idempotent_on_second_call(db_session):
    service = DemoSeedService()
    await service.seed(db_session)

    result = await service.seed(db_session)

    assert result.student_created is False
    assert result.sessions_created == 0
    assert result.fee_records_created == 0

    parent = await ParentRepository().get_by_phone(db_session, STUDENT_PARENT_PHONE)
    children = await ParentRepository().get_students_by_parent_id(db_session, parent.id)
    assert len(children) == 1  # not 2 — no duplicate student
```

Also add the missing import at the top of the test file:
```python
from services.fee_service import FeeService
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_demo_seed_service.py -v`
Expected: FAIL — `AttributeError: 'DemoSeedResult' object has no attribute 'student_created'`

- [ ] **Step 3: Extend `services/demo_seed_service.py`**

Modify the imports at the top of `services/demo_seed_service.py` — replace:
```python
from models.batch_base import BatchSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from services.batch_service import BatchService
from services.fee_service import FeeService
```
with:
```python
from datetime import timedelta

from models.batch_base import BatchSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeStatus
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.student_base import StudentSchema
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from repositories.parent_repository import ParentRepository
from repositories.student_repository import StudentRepository
from services.attendance_service import AttendanceService
from services.batch_service import BatchService
from services.enrollment_service import EnrollmentService
from services.fee_service import FeeService
```

Modify the `DemoSeedResult` dataclass — replace:
```python
@dataclass
class DemoSeedResult:
    owner_created: bool
    institute_created: bool
    batches_created: list[str] = field(default_factory=list)
```
with:
```python
@dataclass
class DemoSeedResult:
    owner_created: bool
    institute_created: bool
    batches_created: list[str] = field(default_factory=list)
    student_created: bool = False
    sessions_created: int = 0
    fee_records_created: int = 0
```

Modify `DemoSeedService.__init__` — replace:
```python
    def __init__(self) -> None:
        self.owner_repo = OwnerRepository()
        self.institute_repo = InstituteRepository()
        self.batch_service = BatchService()
        self.fee_service = FeeService()
```
with:
```python
    def __init__(self) -> None:
        self.owner_repo = OwnerRepository()
        self.institute_repo = InstituteRepository()
        self.parent_repo = ParentRepository()
        self.student_repo = StudentRepository()
        self.batch_service = BatchService()
        self.fee_service = FeeService()
        self.enrollment_service = EnrollmentService()
        self.attendance_service = AttendanceService()
```

Add these three new methods right before `seed()` (after `_seed_batches`):
```python
    async def _seed_parent_and_student(
        self, db: AsyncSession, institute: InstituteSchema, batches: list[BatchSchema]
    ) -> tuple[StudentSchema, list[EnrollmentSchema], bool]:
        parent = await self.parent_repo.get_by_phone(db, STUDENT_PARENT_PHONE)
        existing_children = (
            await self.parent_repo.get_students_by_parent_id(db, parent.id) if parent else []
        )

        if existing_children:
            student = existing_children[0]
            student_created = False
        else:
            enrollment = await self.enrollment_service.invite_student(
                db,
                student_name="Aarav Sharma",
                parent_phone=STUDENT_PARENT_PHONE,
                institute_id=institute.id,
                batch_id=batches[0].id,
                due_day=5,
                parent_name="Rina Sharma",
            )
            student = await self.student_repo.get_by_id(db, enrollment.student_id)
            student_created = True

        for batch in batches:
            try:
                await self.enrollment_service.enroll_student(
                    db, student_id=student.id, batch_id=batch.id, due_day=5
                )
            except ValueError:
                pass  # already enrolled in this batch

        enrollments: list[EnrollmentSchema] = []
        for batch in batches:
            enrollment = await self.enrollment_service.enrollment_repo.get_by_student_and_batch(
                db, student.id, batch.id
            )
            enrollments.append(enrollment)

        return student, enrollments, student_created

    async def _seed_sessions_and_attendance(
        self,
        db: AsyncSession,
        batches: list[BatchSchema],
        enrollments: list[EnrollmentSchema],
    ) -> int:
        today = date.today()
        offsets = [21, 14, 7]  # oldest first
        created = 0
        for batch, enrollment in zip(batches, enrollments, strict=True):
            for i, offset in enumerate(offsets):
                session_date = today - timedelta(days=offset)
                try:
                    session = await self.attendance_service.create_session(
                        db,
                        batch_id=batch.id,
                        session_date=session_date,
                        start_time=batch.start_time,
                        end_time=batch.end_time,
                    )
                except ValueError:
                    continue  # session for this batch+date already exists
                created += 1
                if i > 0:  # mark present for all but the oldest session
                    await self.attendance_service.bulk_mark(db, session.id, [enrollment.id])
        return created

    async def _seed_fee_records(
        self, db: AsyncSession, enrollments: list[EnrollmentSchema]
    ) -> int:
        today = date.today()
        current_month = today.replace(day=1)
        last_month = (current_month - timedelta(days=1)).replace(day=1)

        created = 0
        for enrollment in enrollments:
            for month in (last_month, current_month):
                new_records = await self.fee_service.generate_monthly_records(
                    db, enrollment.batch_id, month
                )
                created += len(new_records)

            last_month_record = await self.fee_service.fee_repo.get_record_by_enrollment_and_month(
                db, enrollment.id, last_month
            )
            if last_month_record and last_month_record.status != FeeStatus.FULLY_PAID:
                await self.fee_service.mark_payment(
                    db,
                    last_month_record.id,
                    last_month_record.amount_due,
                    reference="DEMO-SEED",
                )
        return created
```

Modify `seed()` — replace:
```python
    async def seed(self, db: AsyncSession) -> DemoSeedResult:
        owner, owner_created = await self._seed_owner(db)
        institute, institute_created = await self._seed_institute(db, owner)
        _batches, batches_created = await self._seed_batches(db, institute)

        return DemoSeedResult(
            owner_created=owner_created,
            institute_created=institute_created,
            batches_created=batches_created,
        )
```
with:
```python
    async def seed(self, db: AsyncSession) -> DemoSeedResult:
        owner, owner_created = await self._seed_owner(db)
        institute, institute_created = await self._seed_institute(db, owner)
        batches, batches_created = await self._seed_batches(db, institute)
        _student, enrollments, student_created = await self._seed_parent_and_student(
            db, institute, batches
        )
        sessions_created = await self._seed_sessions_and_attendance(db, batches, enrollments)
        fee_records_created = await self._seed_fee_records(db, enrollments)

        return DemoSeedResult(
            owner_created=owner_created,
            institute_created=institute_created,
            batches_created=batches_created,
            student_created=student_created,
            sessions_created=sessions_created,
            fee_records_created=fee_records_created,
        )
```

Also add `from datetime import date` — check the top-level `from datetime import date, time` import in
the original Task 1 file already covers `date`; only `timedelta` needed adding, already included above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_demo_seed_service.py -v`
Expected: PASS (4 tests total)

Run full suite: `uv run pytest -v`
Expected: all pass, no regressions

- [ ] **Step 5: Lint**

Run: `uv run ruff check services/demo_seed_service.py tests/test_demo_seed_service.py`
Expected: no errors

- [ ] **Step 6: Write scratchpad status file**

Create `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/backend-task-2-parent-student-attendance-fees.md`:

```markdown
# backend-task-2-parent-student-attendance-fees

## Done
- Extended `services/demo_seed_service.py` (built on top of Task 1's file — read
  `backend-task-1-owner-institute-batches.md` first for context) with
  `_seed_parent_and_student`, `_seed_sessions_and_attendance`, `_seed_fee_records`.
- `DemoSeedResult` now has `student_created`, `sessions_created`, `fee_records_created`.
- `seed()` is now the FULL orchestrator — owner, institute, batches, parent/student
  (owner-invite-stub shape, matching `EnrollmentService.invite_student`), 2 enrollments,
  6 class sessions (3 per batch) with attendance, 4 fee records (2 months x 2 batches,
  last month marked FULLY_PAID).
- Idempotency verified for the full graph — `test_seed_is_fully_idempotent_on_second_call`.
- [Fill in: pytest summary line, full suite pass/fail.]

## Not done / known limitations
- No HTTP route yet (Task 3).
- Session dates are relative to `date.today()` — re-running the seed endpoint on a
  DIFFERENT calendar day than a previous run will add new (non-duplicate) session dates
  rather than being a strict no-op; this is intentional per the spec (§8 delivery notes)
  but worth knowing if session counts look higher than expected on a later re-run.

## Where to find it
- `services/demo_seed_service.py` — same file as Task 1, now complete.
- `tests/test_demo_seed_service.py` — same file as Task 1, now 4 tests total.
```

Append to `knowledge_base.md`:
```markdown
| backend-task-2-parent-student-attendance-fees.md | Completes DemoSeedService.seed() — full graph, idempotent, no route yet |
```

- [ ] **Step 7: Commit**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
git add services/demo_seed_service.py tests/test_demo_seed_service.py
git commit -m "$(cat <<'EOF'
feat: complete DemoSeedService with parent/student/attendance/fees

Second half of DemoSeedService — seeds the reviewer-facing student account
(9999999998) via EnrollmentService.invite_student so it has the same
owner-created-stub shape a real WhatsApp invite produces, plus attendance
history and a mix of paid/due fee records for realism.
EOF
)"
```

---

## Task 3: Wire `POST /admin/seed-demo-accounts`

**Files:**
- Create: `routes/responses/seed_demo_accounts_response.py`
- Modify: `routes/admin_route.py`
- Test: `tests/test_admin_route.py`

**Interfaces:**
- Consumes: `DemoSeedService`, `get_demo_seed_service`, `DemoSeedResult` (`services/demo_seed_service.py`, Task 2). `_verify_admin_secret` (already in `routes/admin_route.py`).
- Produces: `POST /admin/seed-demo-accounts` HTTP endpoint. Nothing downstream in this plan consumes it further — this is the final backend deliverable used manually per the spec's delivery checklist (§8 of the spec).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_route.py
"""Integration tests for POST /admin/seed-demo-accounts."""

import os

os.environ.setdefault("ADMIN_BACKFILL_SECRET", "test-admin-secret")


async def test_seed_demo_accounts_requires_admin_secret(client):
    response = await client.post("/admin/seed-demo-accounts")
    assert response.status_code == 401


async def test_seed_demo_accounts_rejects_wrong_secret(client):
    response = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "wrong"}
    )
    assert response.status_code == 401


async def test_seed_demo_accounts_creates_data(client):
    response = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "test-admin-secret"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["owner_created"] is True
    assert body["institute_created"] is True
    assert sorted(body["batches_created"]) == ["Class 10 Maths", "Class 12 Physics"]
    assert body["student_created"] is True
    assert body["sessions_created"] == 6
    assert body["fee_records_created"] == 4


async def test_seed_demo_accounts_is_idempotent_via_http(client):
    first = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "test-admin-secret"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "test-admin-secret"}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["owner_created"] is False
    assert body["institute_created"] is False
    assert body["batches_created"] == []
    assert body["student_created"] is False
    assert body["sessions_created"] == 0
    assert body["fee_records_created"] == 0
```

Note: `ADMIN_BACKFILL_SECRET` must be set **before** `config.get_settings()` is first called
(it's `@lru_cache`d). `tests/conftest.py` sets other required env vars the same way at import
time — this test file's `os.environ.setdefault` at module level follows that same pattern and
runs before `app` (and therefore `get_settings()`) is imported by `conftest.py`. If this
causes a fixture ordering issue, move the `os.environ.setdefault` call into `tests/conftest.py`
itself, next to the existing `os.environ.setdefault(...)` calls, instead.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_admin_route.py -v`
Expected: FAIL — first test gets 404 (route doesn't exist) instead of 401

- [ ] **Step 3: Create the response schema**

```python
# routes/responses/seed_demo_accounts_response.py
from pydantic import BaseModel


class SeedDemoAccountsResponse(BaseModel):
    owner_created: bool
    institute_created: bool
    batches_created: list[str]
    student_created: bool
    sessions_created: int
    fee_records_created: int
```

- [ ] **Step 4: Wire the route in `routes/admin_route.py`**

Modify the imports at the top of `routes/admin_route.py` — replace:
```python
from routes.requests.backfill_payment_links_request import BackfillPaymentLinksRequest
from routes.requests.generate_site_request import GenerateSiteRequest
from routes.responses.backfill_payment_links_response import BackfillPaymentLinksResponse
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service
```
with:
```python
from routes.requests.backfill_payment_links_request import BackfillPaymentLinksRequest
from routes.requests.generate_site_request import GenerateSiteRequest
from routes.responses.backfill_payment_links_response import BackfillPaymentLinksResponse
from routes.responses.seed_demo_accounts_response import SeedDemoAccountsResponse
from services.demo_seed_service import DemoSeedService, get_demo_seed_service
from services.fee_service import FeeService, get_fee_service
from services.institute_service import InstituteService, get_institute_service
```

Modify the `Dep` type aliases — replace:
```python
FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]
```
with:
```python
FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]
DemoSeedServiceDep = Annotated[DemoSeedService, Depends(get_demo_seed_service)]
```

Add this new endpoint at the end of the file (after `generate_site`):
```python
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
    same production service methods real signups go through."""
    try:
        result = await demo_seed_service.seed(db)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Demo seed failed — check logs")
    return SeedDemoAccountsResponse(
        owner_created=result.owner_created,
        institute_created=result.institute_created,
        batches_created=result.batches_created,
        student_created=result.student_created,
        sessions_created=result.sessions_created,
        fee_records_created=result.fee_records_created,
    )
```

No change needed to `app.py` — `admin_router` is already registered (`app.py:181`,
`app.include_router(router=admin_router)`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_admin_route.py -v`
Expected: PASS (4 tests)

Run full suite: `uv run pytest -v`
Expected: all pass

- [ ] **Step 6: Lint**

Run: `uv run ruff check routes/admin_route.py routes/responses/seed_demo_accounts_response.py tests/test_admin_route.py`
Expected: no errors

- [ ] **Step 7: Manual smoke test against local Docker stack**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
make dev-d
sleep 3
curl -s -X POST http://localhost:8000/admin/seed-demo-accounts \
  -H "X-Admin-Secret: $(grep ADMIN_BACKFILL_SECRET .env | cut -d= -f2)" | python3 -m json.tool
```
Expected: JSON body with `owner_created: true`, `institute_created: true`,
`batches_created: ["Class 10 Maths", "Class 12 Physics"]`, `student_created: true`,
`sessions_created: 6`, `fee_records_created: 4`. If `ADMIN_BACKFILL_SECRET` is not set in
your local `.env`, add it first (any random string) — the endpoint returns 503 without it.

- [ ] **Step 8: Write scratchpad status file**

Create `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/backend-task-3-seed-endpoint.md`:

```markdown
# backend-task-3-seed-endpoint

## Done
- `routes/responses/seed_demo_accounts_response.py` — new `SeedDemoAccountsResponse` schema.
- `routes/admin_route.py` — new `POST /admin/seed-demo-accounts`, gated by the existing
  `_verify_admin_secret` (`X-Admin-Secret` header), calling `DemoSeedService.seed()` from
  Tasks 1+2.
- No `app.py` change needed — `admin_router` was already registered.
- Manually smoke-tested against local Docker stack: [Fill in: paste the curl JSON response
  you actually got].
- [Fill in: pytest summary line.]

## Not done
- This is the last backend task — the endpoint is not yet called against the PRODUCTION
  database. That's a manual step in the spec's §8 delivery checklist
  (`docs/superpowers/specs/2026-07-10-play-store-reviewer-access-design.md`), to be run by
  a human (or a dedicated ops task) right before Play Store submission, not part of this
  implementation plan.

## Where to find it
- `routes/responses/seed_demo_accounts_response.py` — new file.
- `routes/admin_route.py` — modified, new endpoint at the bottom of the file.
- `tests/test_admin_route.py` — new file, 4 tests.
- Backend demo-seed feature is now COMPLETE end-to-end. See
  `backend-task-1-owner-institute-batches.md` and
  `backend-task-2-parent-student-attendance-fees.md` for the service-layer half.
```

Append to `knowledge_base.md`:
```markdown
| backend-task-3-seed-endpoint.md | POST /admin/seed-demo-accounts wired + tested — backend work COMPLETE |
```

- [ ] **Step 9: Commit**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
git add routes/admin_route.py routes/responses/seed_demo_accounts_response.py tests/test_admin_route.py
git commit -m "$(cat <<'EOF'
feat: add POST /admin/seed-demo-accounts endpoint

Exposes DemoSeedService over HTTP behind the existing X-Admin-Secret gate,
so the Play Store reviewer demo data can be (re-)seeded against prod without
shell access to the database.
EOF
)"
```

---

## Task 4: RN — Student phone-entry screen

**Files:**
- Create: `src/app/(auth)/student-phone-login.tsx`
- Repo: `/Users/bedantsharma/PycharmProjects/BATCHBOOK_APP` (separate git repo, not a submodule)

**Interfaces:**
- Consumes: `api` (`src/services/api.ts`, existing shared axios instance), `AppInput`/`AppButton`/`AppText`/`LogoMark` (`src/components/`), `C`/`spacing` (`src/constants/colors.ts`, `src/constants/spacing.ts`) — all identical imports to the existing `src/app/(auth)/phone-login.tsx`.
- Produces: route `/(auth)/student-phone-login`, navigating forward with `params: { phone }` to `/(auth)/student-otp-verification` (Task 5). Task 6 (onboarding wiring) routes here.

- [ ] **Step 1: Create the screen**

```tsx
// src/app/(auth)/student-phone-login.tsx
import React, { useState } from 'react';
import { View, StyleSheet, Platform, Pressable } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppInput } from '../../components/AppInput';
import { AppButton } from '../../components/AppButton';
import { AppText } from '../../components/AppText';
import { LogoMark } from '../../components/LogoMark';
import C from '../../constants/colors';
import { spacing } from '../../constants/spacing';
import api from '../../services/api';

export default function StudentPhoneLoginScreen() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const validate = (val: string) => /^\d{10}$/.test(val);

  const handleSubmit = async () => {
    if (!validate(phone)) {
      setError('Enter a valid 10-digit mobile number');
      return;
    }
    setError('');
    setLoading(true);
    try {
      await api.post('/parent/generate_otp', { phone });
      router.push({ pathname: '/(auth)/student-otp-verification', params: { phone } } as any);
    } catch {
      // api interceptor already shows toast for non-401 errors
      setError('Could not send OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.kav}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.container}>
          {/* Back */}
          <Pressable onPress={() => router.back()} style={styles.back}>
            <AppText variant="body" color={C.primary}>← Back</AppText>
          </Pressable>

          {/* Header */}
          <View style={styles.header}>
            <LogoMark size={48} />
            <AppText variant="title" style={styles.title}>Student Login</AppText>
            <AppText variant="body" color={C.text2} style={styles.subtitle}>
              We'll send a 6-digit OTP to your parent's mobile number
            </AppText>
          </View>

          {/* Form */}
          <View style={styles.form}>
            <AppInput
              label="Parent's Mobile Number"
              placeholder="10-digit number"
              value={phone}
              onChangeText={(t) => {
                setPhone(t.replace(/\D/g, '').slice(0, 10));
                setError('');
              }}
              keyboardType="phone-pad"
              maxLength={10}
              error={error}
              autoFocus
            />
            <AppButton
              label="Send OTP"
              onPress={handleSubmit}
              loading={loading}
              disabled={phone.length !== 10}
              style={styles.submitBtn}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  kav: { flex: 1 },
  container: { flex: 1, paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  back: { alignSelf: 'flex-start', paddingVertical: spacing.sm },
  header: { alignItems: 'center', gap: spacing.md, marginTop: spacing.xl, marginBottom: spacing.xxxl },
  title: { letterSpacing: -0.5 },
  subtitle: { textAlign: 'center', lineHeight: 20 },
  form: { gap: spacing.xl },
  submitBtn: { marginTop: spacing.sm },
});
```

- [ ] **Step 2: Typecheck and lint**

Run: `cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP && npx tsc --noEmit`
Expected: no errors (the `/(auth)/student-otp-verification` route not existing yet is fine —
it's referenced only as a string literal cast `as any`, same pattern the owner screen uses for
its own forward reference; Task 5 creates the actual file)

Run: `npm run lint`
Expected: no errors

- [ ] **Step 3: Write scratchpad status file**

Create `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/mobile-task-4-student-phone-login-screen.md`:

```markdown
# mobile-task-4-student-phone-login-screen

## Done
- Created `src/app/(auth)/student-phone-login.tsx` in BATCHBOOK_APP (separate repo from
  BatchBook backend — see `backend-task-3-seed-endpoint.md` for the endpoints this screen
  calls: `POST /parent/generate_otp`).
- Mirrors the existing owner screen `src/app/(auth)/phone-login.tsx` exactly, just pointed
  at the parent/student OTP endpoint and route.
- [Fill in: tsc/lint output.]

## Not done
- Not wired into navigation yet — nothing routes to `/(auth)/student-phone-login` until
  Task 6 changes `onboarding.tsx`.
- The screen it navigates TO (`student-otp-verification`) doesn't exist until Task 5.
- Not manually tested on a device/simulator yet (needs Task 5 + Task 6 first).

## Where to find it
- `src/app/(auth)/student-phone-login.tsx` — new file, BATCHBOOK_APP repo.
```

Append to `knowledge_base.md`:
```markdown
| mobile-task-4-student-phone-login-screen.md | New RN screen: student phone entry, calls /parent/generate_otp |
```

- [ ] **Step 4: Commit**

```bash
cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP
git add src/app/\(auth\)/student-phone-login.tsx
git commit -m "$(cat <<'EOF'
feat: add student phone-entry screen

Mirrors the existing owner phone-login screen, pointed at the parent/student
OTP endpoint. First half of the previously-missing student login path.
EOF
)"
```

---

## Task 5: RN — Student OTP-verification screen

**Files:**
- Create: `src/app/(auth)/student-otp-verification.tsx`
- Repo: `/Users/bedantsharma/PycharmProjects/BATCHBOOK_APP`

**Interfaces:**
- Consumes: `api` (`src/services/api.ts`), `supabase` (`src/lib/supabaseClient.ts`), same UI components as Task 4. Receives `phone` route param from Task 4's screen.
- Produces: on success, writes `AsyncStorage` keys `bb_role='student'`, `bb_student_id`, `bb_student_name` (same keys `StudentDataContext`/`(student)/_layout.tsx` already read — confirmed during research, no changes needed there) and navigates to `/(student)/home`.

- [ ] **Step 1: Create the screen**

```tsx
// src/app/(auth)/student-otp-verification.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet, Pressable } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppInput } from '../../components/AppInput';
import { AppButton } from '../../components/AppButton';
import { AppText } from '../../components/AppText';
import { LogoMark } from '../../components/LogoMark';
import C from '../../constants/colors';
import { spacing } from '../../constants/spacing';
import api from '../../services/api';
import { supabase } from '../../lib/supabaseClient';

interface ChildSummary {
  id: number;
  name: string | null;
  fees_status: string;
}

export default function StudentOtpVerificationScreen() {
  const router = useRouter();
  const { phone } = useLocalSearchParams<{ phone: string }>();
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(60);
  const [resending, setResending] = useState(false);

  // Countdown timer: tick every second until it hits 0
  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const verify = useCallback(
    async (code: string) => {
      if (code.length !== 6) return;
      setError('');
      setLoading(true);
      try {
        const { data } = await api.post('/parent/verify_otp', { token: code, phone });
        const children: ChildSummary[] = data.children ?? [];

        if (children.length === 0) {
          setError('No student profile found for this number. Ask your tutor to add you first.');
          setOtp('');
          return;
        }

        // Bridge backend JWT into the Supabase JS client
        const { error: sessionError } = await supabase.auth.setSession({
          access_token: data.auth_token,
          refresh_token: data.refresh_token,
        });
        if (sessionError) throw sessionError;

        // Stamp student role + active child for route guard and dashboard data
        await AsyncStorage.setItem('bb_role', 'student');
        await AsyncStorage.setItem('bb_student_id', String(children[0].id));
        await AsyncStorage.setItem('bb_student_name', children[0].name ?? '');

        router.replace('/(student)/home' as any);
      } catch {
        setError('Invalid OTP. Please try again.');
        setOtp('');
      } finally {
        setLoading(false);
      }
    },
    [phone, router]
  );

  const handleOtpChange = (val: string) => {
    const digits = val.replace(/\D/g, '').slice(0, 6);
    setOtp(digits);
    setError('');
    if (digits.length === 6) verify(digits);
  };

  const handleResend = async () => {
    setResending(true);
    setOtp('');
    setError('');
    try {
      await api.post('/parent/generate_otp', { phone });
      setCountdown(60);
    } catch {
      // toast shown by api interceptor
    } finally {
      setResending(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        {/* Back */}
        <Pressable onPress={() => router.back()} style={styles.back}>
          <AppText variant="body" color={C.primary}>← Back</AppText>
        </Pressable>

        {/* Header */}
        <View style={styles.header}>
          <LogoMark size={48} />
          <AppText variant="title" style={styles.title}>Enter OTP</AppText>
          <AppText variant="body" color={C.text2} style={styles.subtitle}>
            Sent to +91 {phone}
          </AppText>
        </View>

        {/* OTP Input */}
        <View style={styles.otpSection}>
          <AppInput
            label="6-digit OTP"
            placeholder="Enter OTP"
            value={otp}
            onChangeText={handleOtpChange}
            keyboardType="number-pad"
            maxLength={6}
            error={error}
            autoFocus
            textContentType="oneTimeCode"
            style={styles.otpInput}
          />
        </View>

        {/* Verify Button */}
        <AppButton
          label="Verify OTP"
          onPress={() => verify(otp)}
          loading={loading}
          disabled={otp.length !== 6 || loading}
          style={styles.verifyBtn}
        />

        {/* Resend */}
        <View style={styles.resendRow}>
          {countdown > 0 ? (
            <AppText variant="body" color={C.text2}>Resend OTP in {countdown}s</AppText>
          ) : (
            <Pressable onPress={handleResend} disabled={resending}>
              <AppText variant="body" color={resending ? C.text2 : C.primary}>
                {resending ? 'Sending...' : 'Resend OTP'}
              </AppText>
            </Pressable>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  container: { flex: 1, paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  back: { alignSelf: 'flex-start', paddingVertical: spacing.sm },
  header: { alignItems: 'center', gap: spacing.md, marginTop: spacing.xl, marginBottom: spacing.xxxl },
  title: { letterSpacing: -0.5 },
  subtitle: { textAlign: 'center' },
  otpSection: { marginBottom: spacing.xxl },
  otpInput: { textAlign: 'center', fontSize: 22, letterSpacing: 8 },
  verifyBtn: { marginBottom: spacing.xl },
  resendRow: { alignItems: 'center' },
});
```

- [ ] **Step 2: Typecheck and lint**

Run: `cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP && npx tsc --noEmit`
Expected: no errors

Run: `npm run lint`
Expected: no errors

- [ ] **Step 3: Write scratchpad status file**

Create `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/mobile-task-5-student-otp-verification-screen.md`:

```markdown
# mobile-task-5-student-otp-verification-screen

## Done
- Created `src/app/(auth)/student-otp-verification.tsx`. Read
  `mobile-task-4-student-phone-login-screen.md` first — this is the screen that one
  navigates to.
- Calls `POST /parent/verify_otp` (backend: `backend-task-3-seed-endpoint.md` and earlier —
  this endpoint already existed, unchanged by this plan).
- On success: bridges the Supabase session via `supabase.auth.setSession`, writes
  `AsyncStorage` keys `bb_role`, `bb_student_id`, `bb_student_name` (same keys the existing
  `(student)/_layout.tsx` route guard and `StudentDataContext` already read — verified during
  design research, no changes needed to either file), then `router.replace('/(student)/home')`.
- Handles the edge case where the verifying phone has zero linked children (shows an error
  instead of crashing on `children[0]`).
- [Fill in: tsc/lint output.]

## Not done
- End-to-end navigation not wired yet — nothing routes to `/(auth)/student-phone-login` (the
  screen before this one) until Task 6.
- Not manually tested on a device/simulator yet (Task 6 finishes the wiring; the plan's final
  manual-QA task covers actually running this on-device).

## Where to find it
- `src/app/(auth)/student-otp-verification.tsx` — new file, BATCHBOOK_APP repo.
```

Append to `knowledge_base.md`:
```markdown
| mobile-task-5-student-otp-verification-screen.md | New RN screen: OTP verify + AsyncStorage stamping + redirect to (student)/home |
```

- [ ] **Step 4: Commit**

```bash
cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP
git add src/app/\(auth\)/student-otp-verification.tsx
git commit -m "$(cat <<'EOF'
feat: add student OTP-verification screen

Completes the previously-missing student login path: verifies OTP against
/parent/verify_otp, bridges the Supabase session, stamps AsyncStorage role
keys the existing (student) route guard already expects, and redirects to
(student)/home.
EOF
)"
```

---

## Task 6: RN — Wire onboarding's student branch to the new login screens

**Files:**
- Modify: `src/app/(auth)/onboarding.tsx`
- Repo: `/Users/bedantsharma/PycharmProjects/BATCHBOOK_APP`

**Interfaces:**
- Consumes: `/(auth)/student-phone-login` route (Task 4).
- Produces: nothing consumed further in this plan — this is the last mobile code task.

- [ ] **Step 1: Remove the now-dead `Text` import**

Modify `src/app/(auth)/onboarding.tsx` — replace:
```tsx
import { View, StyleSheet, ScrollView, Text } from 'react-native';
```
with:
```tsx
import { View, StyleSheet, ScrollView } from 'react-native';
```

- [ ] **Step 2: Make `handleContinue` navigate for the student branch too**

Modify `src/app/(auth)/onboarding.tsx` — replace:
```tsx
    if (step === 3) {
      setLoading(true);
      try {
        await AsyncStorage.setItem('onboarding_profile', JSON.stringify(profile));
        if (profile.role === 'owner') {
          router.replace('/(auth)/phone-login' as any);
        }
        // student stays on step 3 — shows "ask for join link" message
      } finally {
        setLoading(false);
      }
    }
```
with:
```tsx
    if (step === 3) {
      setLoading(true);
      try {
        await AsyncStorage.setItem('onboarding_profile', JSON.stringify(profile));
        if (profile.role === 'owner') {
          router.replace('/(auth)/phone-login' as any);
        } else if (profile.role === 'student') {
          router.replace('/(auth)/student-phone-login' as any);
        }
      } finally {
        setLoading(false);
      }
    }
```

- [ ] **Step 3: Replace the "Ask your tutor" dead-end with a login CTA**

Modify `src/app/(auth)/onboarding.tsx` — replace:
```tsx
            ) : (
              <>
                <AppText size={32} style={styles.joinIcon}>🔗</AppText>
                <AppText variant="title" style={styles.stepTitle}>Ask your tutor</AppText>
                <AppText variant="body" color={C.text2} style={styles.joinSubtitle}>
                  Ask your tutor to send you a BatchBook join link. It looks like:
                </AppText>
                <View style={styles.joinCodeBox}>
                  <Text style={styles.joinCodeText}>batchbook://join/ABC123</Text>
                </View>
                <AppButton
                  label="Done"
                  onPress={() => router.replace('/(auth)/landing' as any)}
                  variant="secondary"
                  style={styles.doneBtn}
                />
              </>
            )}
```
with:
```tsx
            ) : (
              <>
                <AppText size={32} style={styles.joinIcon}>🎓</AppText>
                <AppText variant="title" style={styles.stepTitle}>Almost there!</AppText>
                <AppText variant="body" color={C.text2} style={styles.joinSubtitle}>
                  Login with your parent's mobile number to see your schedule, attendance, and fees
                </AppText>
                <AppButton
                  label="Continue to Login →"
                  onPress={handleContinue}
                  loading={loading}
                  style={styles.doneBtn}
                />
              </>
            )}
```

- [ ] **Step 4: Remove the now-unused `joinCodeBox`/`joinCodeText` styles**

Modify `src/app/(auth)/onboarding.tsx` — replace:
```tsx
  joinIcon: { textAlign: 'center', marginBottom: spacing.lg },
  joinSubtitle: { lineHeight: 20, marginBottom: 20 },
  joinCodeBox: {
    backgroundColor: C.surface2,
    borderRadius: radius.md,
    padding: 14,
    marginBottom: spacing.xxl,
    alignItems: 'center',
  },
  joinCodeText: {
    fontSize: 13,
    color: C.primary,
    fontWeight: '600',
    fontFamily: 'DMSans_600SemiBold',
    letterSpacing: 0.5,
  },
});
```
with:
```tsx
  joinIcon: { textAlign: 'center', marginBottom: spacing.lg },
  joinSubtitle: { lineHeight: 20, marginBottom: 20 },
});
```

Check whether `radius` (imported from `'../../constants/colors'`) is still used elsewhere in this
file after this removal — search the file for `radius.` If `joinCodeBox` was its only use, also
change the import line from:
```tsx
import C, { radius } from '../../constants/colors';
```
to:
```tsx
import C from '../../constants/colors';
```

- [ ] **Step 5: Typecheck and lint**

Run: `cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP && npx tsc --noEmit`
Expected: no errors

Run: `npm run lint`
Expected: no errors (this step should also catch it if `radius` or `Text` ended up unused/still-imported incorrectly)

- [ ] **Step 6: Manual QA — full student login flow on-device/simulator**

This step needs a human (or an agent with device/simulator access, which this plan's executor
may not have — if so, stop here and hand off to the user with a clear note in the scratchpad
file, per the template below):

1. `cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP && npm run start`, open on a device/
   simulator (Expo Go or a dev build).
2. From the landing screen, tap "I'm a Student".
3. Enter name "Aarav Sharma" (or any name — this screen's `name` field isn't sent to the
   backend, only `parentPhone` matters for login) and parent phone `9999999998`, tap Continue.
4. On step 3, tap "Continue to Login →" — should navigate to the new phone-entry screen,
   pre-filled with nothing (phone is re-entered here, this is intentional — matches the owner
   flow's UX where onboarding profile fields and the actual login phone are separate steps).
5. Enter `9999999998`, tap "Send OTP".
6. On the OTP screen, enter `110304`.
7. Expect: navigation to `/(student)/home` showing "Aarav Sharma" and the two seeded batches'
   schedule/attendance/fee data (requires `POST /admin/seed-demo-accounts` to have been run
   against whatever backend this device is pointed at — local dev, per Task 3 Step 7).
8. Confirm the existing owner flow (`9999999999` / `110304`) still works unchanged.

- [ ] **Step 7: Write scratchpad status file**

Create `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/mobile-task-6-onboarding-wire-student-flow.md`:

```markdown
# mobile-task-6-onboarding-wire-student-flow

## Done
- Modified `src/app/(auth)/onboarding.tsx`: student branch of `handleContinue` now navigates
  to `/(auth)/student-phone-login` (Task 4's screen) instead of doing nothing; step-3 JSX for
  the student role now shows a "Continue to Login →" CTA instead of the static "Ask your
  tutor" join-code card; removed now-unused `Text` import and `joinCodeBox`/`joinCodeText`
  styles (and the `radius` import, if it turned out unused — [Fill in: was it?]).
- This completes the mobile side of the feature: Owner login (pre-existing) + Student login
  (Tasks 4, 5, 6, all in this scratchpad folder) both now reach working screens.
- tsc/lint: [Fill in output]

## Not done / handed off to human
- [Fill in: did you actually run Step 6's manual on-device QA? If you don't have
  device/simulator access, say so explicitly here — don't claim it passed if you didn't
  run it. State clearly: "Manual on-device QA NOT performed — needs a human with a
  simulator/device. Steps to follow are in Task 6 Step 6 of the plan at
  docs/superpowers/plans/2026-07-10-play-store-reviewer-access.md in the BatchBook repo."]
- Production seeding (`POST /admin/seed-demo-accounts` against the prod DB) and the Play
  Store "App access" reviewer-credentials field are both manual, out-of-repo steps — see
  spec §8 (`docs/superpowers/specs/2026-07-10-play-store-reviewer-access-design.md` in
  BatchBook).

## Where to find it
- `src/app/(auth)/onboarding.tsx` — modified, BATCHBOOK_APP repo.
- Full feature summary: read all 6 files in this scratchpad folder in order
  (backend-task-1 through mobile-task-6) plus `knowledge_base.md` for the one-line index.
```

Append to `knowledge_base.md`:
```markdown
| mobile-task-6-onboarding-wire-student-flow.md | Wires onboarding -> student-phone-login; FEATURE COMPLETE pending manual QA + prod seed |
```

- [ ] **Step 8: Commit**

```bash
cd /Users/bedantsharma/PycharmProjects/BATCHBOOK_APP
git add src/app/\(auth\)/onboarding.tsx
git commit -m "$(cat <<'EOF'
feat: wire student onboarding to the new login screens

Replaces the dead-end "ask your tutor for a join link" card with a working
navigation to the new student phone-login/OTP-verification screens, so
picking "I'm a Student" now reaches a functioning login instead of a
static message.
EOF
)"
```

---

## Delivery notes (not execution tasks — read before wrapping up)

- Backend and mobile are **separate git repos** — Tasks 1-3 commit in `BatchBook`, Tasks 4-6
  commit in `BATCHBOOK_APP`. Neither needs a submodule-pointer bump in the other (BATCHBOOK_APP
  is a sibling repo, not a submodule of BatchBook).
- Before Play Store submission, a human must still do the three manual steps in the spec's §8:
  confirm the Supabase Test OTP config, call `POST /admin/seed-demo-accounts` against the
  **production** `DATABASE_URL`/backend, and walk both logins on the actual Play Store build.
- When this branch/PR is ready for review, point the reviewing agent at
  `/Users/bedantsharma/PycharmProjects/scratchPadForSubAgents/knowledge_base.md` first, then
  the individual task files, for full context on what changed and why — per the user's request,
  this folder is intentionally **not committed to either repo** (it's coordination scratch
  space, not part of the diff).
