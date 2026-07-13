# Returning-Student Flow (Backend + Website) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-gated pre-OTP profile form with a single post-OTP "what's missing?" check, and add the two `PATCH` endpoints needed to fill in whatever's missing, for both the backend and the `batchbookui` website.

**Architecture:** No DB migration — `Parent.name`, `Student.name`, `Student.email` already exist. Two new `PATCH` endpoints reuse the existing `ParentRepository`/`StudentRepository` update methods. `VerifyParentResponse` grows two fields (`parent_name`, `children[].email`) so the client can compute "what's missing" from the OTP-verify response itself, no extra round trip. The website's `OnboardingWizard` drops its pre-OTP name/phone form for students and adds a post-OTP `CompleteProfileStep`; `StudentRoute` gains a session-restore fallback that calls `GET /parent/me` when the cached role is missing.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic (backend), React 19 + MUI + Vitest/RTL (`batchbookui`).

**Companion plan:** `BATCHBOOK_APP/docs/superpowers/plans/2026-07-11-returning-student-flow.md` covers the Expo app side against this same backend contract.

## Global Constraints

- No `Parent.email` column — only `Parent.name` and the existing `Student.email`/`Student.name` are in scope (per the design doc's explicit scope cut).
- Name validation pattern `^[a-zA-Z ]+$` (matches `DTO/student_model.py:13`), email validation pattern `^[^@\s]+@[^@\s]+\.[^@\s]+$` (matches `routes/requests/update_owner_request.py:6`) — reuse both verbatim for the new request schemas.
- Backend tests use the `client` and `db_session` pytest fixtures already defined in `tests/conftest.py` — don't redefine them.
- `PATCH /parent/children/{student_id}` must 403 (not 404 or silent no-op) when the child belongs to a different parent — this is a correctness requirement from the design doc, not a nice-to-have.
- Website tests run via `npm run test` (`vitest run`) inside `batchbookui/`; follow the existing `vi.mock('../lib/supabaseClient', ...)` pattern used in `PhoneOtpStep.test.jsx` rather than hitting a real Supabase client.
- `batchbookui/` is a git submodule with its own remote — commit inside `batchbookui/` first, then bump the pointer in the parent `BatchBook` repo, per `BatchBook/CLAUDE.md`'s submodule rules.

---

## Task 1: `verify_otp` returns parent name + child email

**Files:**
- Modify: `routes/responses/verify_parent_response.py`
- Modify: `services/parent_service.py:42-70` (`verify_otp`)
- Modify: `routes/parent_route.py:57-96` (`verify_otp` handler)
- Modify: `routes/student_route.py:68-112` (`verify_otp` handler — same underlying service call, must stay in sync)
- Test: `tests/test_parent_service.py`
- Test: `tests/test_parent_routes.py`

**Interfaces:**
- Consumes: existing `ParentService.get_or_create_after_otp(db, user_id, phone, name) -> ParentSchema` (unchanged).
- Produces: `ParentService.verify_otp(...) -> tuple[str, str, str, UUID, str | None, list[StudentSchema]]` — six-element tuple now (added `parent_name` as the 5th element, before `children`). Both `routes/parent_route.py` and `routes/student_route.py` verify_otp handlers depend on this exact shape.

- [ ] **Step 1: Write the failing service test**

Update the existing test in `tests/test_parent_service.py` (replace `test_verify_otp_returns_token_and_children_on_success`):

```python
async def test_verify_otp_returns_token_parent_name_and_children_on_success(service):
    user_id = uuid4()
    mock_user = MagicMock()
    mock_user.id = str(user_id)
    mock_user.aud = "authenticated"

    mock_session = MagicMock()
    mock_session.access_token = "access_tok_1234567890"
    mock_session.refresh_token = "refresh_tok_1234567890"

    mock_data = MagicMock()
    mock_data.user = mock_user
    mock_data.session = mock_session

    mock_supabase = MagicMock()
    mock_supabase.auth.verify_otp = AsyncMock(return_value=mock_data)

    parent = _make_parent_schema(user_id=user_id)
    parent.name = "Test Parent"
    child = _make_student_schema(parent_id=parent.id)
    child.email = "child@test.com"

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)
    service.parent_repo.get_by_phone = AsyncMock(return_value=None)
    service.parent_repo.create_parent = AsyncMock(return_value=parent)
    service.parent_repo.get_students_by_parent_id = AsyncMock(return_value=[child])

    (
        access_token,
        refresh_token,
        aud,
        returned_user_id,
        parent_name,
        children,
    ) = await service.verify_otp(
        supabase=mock_supabase,
        db=MagicMock(),
        phone="9876543210",
        token="123456",
        name="Test Parent",
    )

    assert access_token == "access_tok_1234567890"
    assert refresh_token == "refresh_tok_1234567890"
    assert aud == "authenticated"
    assert returned_user_id == user_id
    assert parent_name == "Test Parent"
    assert len(children) == 1
    assert children[0].email == "child@test.com"
```

Also delete the old 5-tuple assertion body from `test_verify_otp_returns_token_and_children_on_success` (renamed above) — don't leave both versions in the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest tests/test_parent_service.py::test_verify_otp_returns_token_parent_name_and_children_on_success -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 6, got 5)`

- [ ] **Step 3: Update `VerifyParentResponse` schema**

Replace the full contents of `routes/responses/verify_parent_response.py`:

```python
from pydantic import BaseModel, Field


class StudentSummaryInToken(BaseModel):
    id: int
    name: str | None
    email: str | None
    fees_status: str

    model_config = {"from_attributes": True}


class VerifyParentResponse(BaseModel):
    auth_token: str = Field(min_length=10)
    refresh_token: str = Field(min_length=10)
    aud: str = Field(...)
    user_id: str = Field(...)
    parent_name: str | None = None
    children: list[StudentSummaryInToken] = []
```

- [ ] **Step 4: Update `ParentService.verify_otp`**

In `services/parent_service.py`, replace the `verify_otp` method:

```python
    async def verify_otp(
        self,
        supabase: AsyncClient,
        db: AsyncSession,
        phone: str,
        token: str,
        name: str | None,
    ) -> tuple[str, str, str, UUID, str | None, list[StudentSchema]]:
        """Verify OTP, upsert parent, return (access_token, refresh_token, aud, user_id, parent_name, children)."""
        try:
            data = await supabase.auth.verify_otp({
                "phone": f"+91{phone}",
                "token": token,
                "type": "sms",
            })
        except Exception as e:
            raise ValueError(str(e)) from e
        if not data.user or not data.session:
            raise ValueError("OTP verification failed")
        user_id = UUID(str(data.user.id))
        parent = await self.get_or_create_after_otp(db, user_id, phone, name)
        children = await self.parent_repo.get_students_by_parent_id(db, parent.id)
        return (
            data.session.access_token,
            data.session.refresh_token,
            data.user.aud,
            user_id,
            parent.name,
            children,
        )
```

- [ ] **Step 5: Run service test to verify it passes**

Run: `uv run pytest tests/test_parent_service.py -v`
Expected: PASS (all tests in the file, including the two other `verify_otp` tests which don't unpack the tuple and are unaffected)

- [ ] **Step 6: Write the failing route test**

Update `tests/test_parent_routes.py` — replace `test_verify_otp_returns_token_and_children_on_success`:

```python
async def test_verify_otp_returns_token_parent_name_and_children_on_success(client):
    user_id = uuid4()
    child = _make_student_schema()
    mock_service = MagicMock(spec=ParentService)
    mock_service.verify_otp = AsyncMock(
        return_value=(
            "access_tok_1234567890",
            "refresh_tok_1234567890",
            "authenticated",
            user_id,
            "Test Parent",
            [child],
        )
    )

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.post("/parent/verify_otp", json={
        "phone": "9876543210",
        "token": "123456",
        "name": "Test Parent",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["parent_name"] == "Test Parent"
    assert len(body["children"]) == 1
    assert body["children"][0]["name"] == "Test Child"
    assert body["children"][0]["email"] == "child@test.com"
```

- [ ] **Step 7: Run route test to verify it fails**

Run: `uv run pytest tests/test_parent_routes.py::test_verify_otp_returns_token_parent_name_and_children_on_success -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 6, got 5)` (the route handler still unpacks 5 values)

- [ ] **Step 8: Update `routes/parent_route.py`'s `verify_otp` handler**

Replace the handler body in `routes/parent_route.py`:

```python
@router.post(
    "/verify_otp",
    summary="Verify OTP and upsert parent record; returns JWT + list of children",
    response_model=VerifyParentResponse,
)
@limiter.limit("10/minute")
async def verify_otp(
    request: Request,
    verify_request: ParentVerifyOtpRequest,
    parent_service: ParentServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        (
            access_token,
            refresh_token,
            aud,
            user_id,
            parent_name,
            children,
        ) = await parent_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=verify_request.phone,
            token=verify_request.token,
            name=verify_request.name,
        )
    except (ValueError, AuthApiError) as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="OTP verification failed due to a server error — check backend logs.",
        )
    children_summary = [
        StudentSummaryInToken(id=c.id, name=c.name, email=c.email, fees_status=c.fees_status.value)
        for c in children
    ]
    return VerifyParentResponse(
        auth_token=access_token,
        refresh_token=refresh_token,
        aud=aud,
        user_id=str(user_id),
        parent_name=parent_name,
        children=children_summary,
    )
```

- [ ] **Step 9: Update `routes/student_route.py`'s `verify_otp` handler the same way**

Replace the handler body in `routes/student_route.py` (same shape, same import already present since it imports `StudentSummaryInToken, VerifyParentResponse` from the same response module):

```python
@router.post(
    "/verify_otp",
    summary="Verify OTP; upserts Parent record and returns JWT + list of children",
    description=(
        "Verifies the SMS OTP. On success, creates or retrieves the Parent record "
        "and returns an access token plus the list of child Student records linked to this parent. "
        "Use POST /parent/verify_otp for the canonical endpoint."
    ),
    response_model=VerifyParentResponse,
)
@limiter.limit("10/minute")
async def verify_otp(
    request: Request,
    verify_request: OtpVerifyRequest,
    parent_service: ParentServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        (
            access_token,
            refresh_token,
            aud,
            user_id,
            parent_name,
            children,
        ) = await parent_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=verify_request.phone,
            token=verify_request.token,
            name=verify_request.name,
        )
    except (ValueError, AuthApiError) as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="OTP verification failed due to a server error — check backend logs.",
        )
    children_summary = [
        StudentSummaryInToken(id=c.id, name=c.name, email=c.email, fees_status=c.fees_status.value)
        for c in children
    ]
    return VerifyParentResponse(
        auth_token=access_token,
        refresh_token=refresh_token,
        aud=aud,
        user_id=str(user_id),
        parent_name=parent_name,
        children=children_summary,
    )
```

- [ ] **Step 10: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS — every test, including `tests/test_parent_service.py`, `tests/test_parent_routes.py`, and anything touching `/student/verify_otp` or the demo-seed flow (`services/demo_seed_service.py` calls `EnrollmentService.invite_student`, not `verify_otp`, so it's unaffected).

- [ ] **Step 11: Commit**

```bash
git add routes/responses/verify_parent_response.py services/parent_service.py routes/parent_route.py routes/student_route.py tests/test_parent_service.py tests/test_parent_routes.py
git commit -m "feat: return parent name + child email from verify_otp for missing-field detection"
```

---

## Task 2: `PATCH /parent/update` endpoint

**Files:**
- Create: `routes/requests/update_parent_request.py`
- Modify: `routes/parent_route.py`
- Test: `tests/test_parent_routes.py`

**Interfaces:**
- Consumes: existing `ParentService.update_parent(db, user_id, updates: dict) -> ParentSchema | None` (`services/parent_service.py:88-94`, unchanged) and existing `ParentService.get_children(db, user_id) -> list[StudentSchema]` (unchanged).
- Produces: `PATCH /parent/update` HTTP route returning `ParentProfileResponse`.

- [ ] **Step 1: Write the failing route test**

Add to `tests/test_parent_routes.py`:

```python
# --- PATCH /parent/update ---

async def test_update_parent_returns_updated_profile(client):
    user_id = uuid4()
    updated_parent = _make_parent_schema(user_id=user_id)
    updated_parent.name = "New Name"

    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.update_parent = AsyncMock(return_value=updated_parent)
    mock_service.get_children = AsyncMock(return_value=[])

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.patch(
        "/parent/update",
        json={"name": "New Name"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Name"
    call_kwargs = mock_service.update_parent.call_args.kwargs
    assert call_kwargs["user_id"] == user_id
    assert call_kwargs["updates"] == {"name": "New Name"}


async def test_update_parent_returns_404_when_not_found(client):
    user_id = uuid4()
    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.update_parent = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.patch(
        "/parent/update",
        json={"name": "New Name"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404


async def test_update_parent_returns_401_without_auth(client):
    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(side_effect=Exception("bad token"))

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.patch(
        "/parent/update",
        json={"name": "New Name"},
        headers={"Authorization": "Bearer badtoken"},
    )

    assert response.status_code == 401
```

`pytest` and `uuid4` are already imported at the top of `tests/test_parent_routes.py` (lines 13–15) — no new imports needed for this test.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parent_routes.py::test_update_parent_returns_updated_profile -v`
Expected: FAIL — `404 Not Found` (no such route exists yet)

- [ ] **Step 3: Create the request schema**

Create `routes/requests/update_parent_request.py`:

```python
from pydantic import BaseModel, Field


class UpdateParentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-zA-Z ]+$")
```

- [ ] **Step 4: Add the route**

In `routes/parent_route.py`, add the import:

```python
from routes.requests.update_parent_request import UpdateParentRequest
```

Add the route (place it after `GET /parent/me`, before `POST /parent/refresh`):

```python
@router.patch(
    "/update",
    summary="Update the authenticated parent's own profile (name)",
    response_model=ParentProfileResponse,
)
async def update_parent(
    update_request: UpdateParentRequest,
    parent_service: ParentServiceDep,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    updates = update_request.model_dump(exclude_none=True)
    updated = await parent_service.update_parent(db=db, user_id=user_id, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Parent record not found")
    children = await parent_service.get_children(db=db, user_id=user_id)
    children_summary = [
        StudentSummary(
            id=c.id,
            name=c.name,
            email=c.email,
            fees_status=c.fees_status.value,
            institute_id=c.institute_id,
        )
        for c in children
    ]
    return ParentProfileResponse(
        id=updated.id,
        name=updated.name,
        phone_number=updated.phone_number,
        created_at=updated.created_at,
        children=children_summary,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_parent_routes.py -v`
Expected: PASS — all three new tests plus the existing suite.

- [ ] **Step 6: Commit**

```bash
git add routes/requests/update_parent_request.py routes/parent_route.py tests/test_parent_routes.py
git commit -m "feat: add PATCH /parent/update endpoint"
```

---

## Task 3: `PATCH /parent/children/{student_id}` endpoint

**Files:**
- Create: `routes/requests/update_child_request.py`
- Modify: `services/parent_service.py`
- Modify: `routes/parent_route.py`
- Test: `tests/test_parent_service.py`
- Test: `tests/test_parent_routes.py`

**Interfaces:**
- Consumes: `StudentRepository.get_by_id(db, student_id) -> StudentSchema | None` and `StudentRepository.update_student(db, student, updates: dict) -> StudentSchema` (`repositories/student_repository.py:14-27`, unchanged); `ParentRepository.get_by_user_id` (unchanged).
- Produces: `ParentService.update_child(db, user_id, student_id, updates: dict) -> StudentSchema | None`, raising `PermissionError` when the student belongs to a different parent. `PATCH /parent/children/{student_id}` HTTP route returning `StudentSummary`.

- [ ] **Step 1: Write the failing service tests**

Add to `tests/test_parent_service.py`:

```python
# --- update_child ---

async def test_update_child_applies_changes_when_owned(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    student = _make_student_schema(parent_id=parent.id)
    updated_student = _make_student_schema(parent_id=parent.id)
    updated_student.email = "new@test.com"

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.student_repo = MagicMock()
    service.student_repo.get_by_id = AsyncMock(return_value=student)
    service.student_repo.update_student = AsyncMock(return_value=updated_student)

    result = await service.update_child(
        db=MagicMock(), user_id=user_id, student_id=student.id, updates={"email": "new@test.com"}
    )
    assert result.email == "new@test.com"


async def test_update_child_raises_permission_error_when_not_owned(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    other_parents_student = _make_student_schema(parent_id=999)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.student_repo = MagicMock()
    service.student_repo.get_by_id = AsyncMock(return_value=other_parents_student)

    with pytest.raises(PermissionError):
        await service.update_child(
            db=MagicMock(), user_id=user_id, student_id=999, updates={"email": "x@test.com"}
        )


async def test_update_child_returns_none_when_student_not_found(service):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)

    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=parent)
    service.student_repo = MagicMock()
    service.student_repo.get_by_id = AsyncMock(return_value=None)

    result = await service.update_child(
        db=MagicMock(), user_id=user_id, student_id=404, updates={"email": "x@test.com"}
    )
    assert result is None


async def test_update_child_returns_none_when_parent_not_found(service):
    service.parent_repo = MagicMock()
    service.parent_repo.get_by_user_id = AsyncMock(return_value=None)
    service.student_repo = MagicMock()

    result = await service.update_child(
        db=MagicMock(), user_id=uuid4(), student_id=1, updates={"email": "x@test.com"}
    )
    assert result is None
    service.student_repo.get_by_id.assert_not_called()
```

`pytest` is already imported at the top of `tests/test_parent_service.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_parent_service.py::test_update_child_applies_changes_when_owned -v`
Expected: FAIL — `AttributeError: 'ParentService' object has no attribute 'update_child'` (and `service.student_repo` doesn't exist yet either)

- [ ] **Step 3: Add `StudentRepository` to `ParentService` and implement `update_child`**

In `services/parent_service.py`, update the imports and constructor, and add the method:

```python
from repositories.student_repository import StudentRepository
```

```python
class ParentService:
    def __init__(self):
        self.parent_repo = ParentRepository()
        self.student_repo = StudentRepository()
```

Add after `update_parent`:

```python
    async def update_child(
        self, db: AsyncSession, user_id: UUID, student_id: int, updates: dict
    ) -> StudentSchema | None:
        parent = await self.parent_repo.get_by_user_id(db, user_id)
        if not parent:
            return None
        student = await self.student_repo.get_by_id(db, student_id)
        if not student:
            return None
        if student.parent_id != parent.id:
            raise PermissionError("This child does not belong to the authenticated parent")
        return await self.student_repo.update_student(db, student, updates)
```

- [ ] **Step 4: Run service tests to verify they pass**

Run: `uv run pytest tests/test_parent_service.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing route tests**

Add to `tests/test_parent_routes.py`:

```python
# --- PATCH /parent/children/{student_id} ---

async def test_update_child_returns_updated_student(client):
    user_id = uuid4()
    updated_child = _make_student_schema()
    updated_child.email = "new@test.com"

    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.update_child = AsyncMock(return_value=updated_child)

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.patch(
        "/parent/children/10",
        json={"email": "new@test.com"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "new@test.com"


async def test_update_child_returns_403_when_not_owned(client):
    user_id = uuid4()
    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.update_child = AsyncMock(
        side_effect=PermissionError("This child does not belong to the authenticated parent")
    )

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.patch(
        "/parent/children/999",
        json={"email": "new@test.com"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 403


async def test_update_child_returns_404_when_not_found(client):
    user_id = uuid4()
    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.update_child = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.patch(
        "/parent/children/404",
        json={"email": "new@test.com"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
```

- [ ] **Step 6: Run route tests to verify they fail**

Run: `uv run pytest tests/test_parent_routes.py::test_update_child_returns_updated_student -v`
Expected: FAIL — `404 Not Found` (no such route exists yet)

- [ ] **Step 7: Create the request schema**

Create `routes/requests/update_child_request.py`:

```python
from pydantic import BaseModel, Field


class UpdateChildRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[a-zA-Z ]+$")
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
```

- [ ] **Step 8: Add the route**

In `routes/parent_route.py`, add the import:

```python
from routes.requests.update_child_request import UpdateChildRequest
```

Add the route (place it after the new `PATCH /parent/update`):

```python
@router.patch(
    "/children/{student_id}",
    summary="Update a linked child's name/email",
    response_model=StudentSummary,
)
async def update_child(
    student_id: int,
    update_request: UpdateChildRequest,
    parent_service: ParentServiceDep,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(_get_current_user_id),
):
    updates = update_request.model_dump(exclude_none=True)
    try:
        updated = await parent_service.update_child(
            db=db, user_id=user_id, student_id=student_id, updates=updates
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Child record not found")
    return StudentSummary(
        id=updated.id,
        name=updated.name,
        email=updated.email,
        fees_status=updated.fees_status.value,
        institute_id=updated.institute_id,
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `uv run pytest tests/test_parent_routes.py -v`
Expected: PASS — all three new tests plus the existing suite.

- [ ] **Step 10: Run the full backend suite**

Run: `uv run pytest -v`
Expected: PASS, all tests.

- [ ] **Step 11: Commit**

```bash
git add routes/requests/update_child_request.py services/parent_service.py routes/parent_route.py tests/test_parent_service.py tests/test_parent_routes.py
git commit -m "feat: add PATCH /parent/children/{student_id} endpoint with ownership check"
```

---

## Task 4: Website — phone/OTP-first student onboarding + `CompleteProfileStep`

**Files:**
- Create: `batchbookui/src/lib/profileCompleteness.js`
- Create: `batchbookui/src/components/onboarding/CompleteProfileStep.jsx`
- Modify: `batchbookui/src/components/onboarding/OnboardingWizard.jsx`
- Modify: `batchbookui/src/components/onboarding/PhoneOtpStep.jsx`
- Delete: `batchbookui/src/components/onboarding/ParentDetailsStep.jsx`
- Modify: `batchbookui/src/App.jsx`
- Test: `batchbookui/src/test/profileCompleteness.test.js`
- Test: `batchbookui/src/test/CompleteProfileStep.test.jsx`
- Test: `batchbookui/src/test/PhoneOtpStep.test.jsx`

**Interfaces:**
- Consumes: backend `PATCH /parent/update` and `PATCH /parent/children/{id}` from Tasks 2–3; `VerifyParentResponse` now includes `parent_name` and `children[].email` from Task 1; existing `api` axios instance (`batchbookui/src/services/api.js`) for authenticated calls.
- Produces: `computeMissingFields(parentName, child) -> { parentName: bool, childEmail: bool }` and `hasMissingFields(missing) -> bool` from `profileCompleteness.js` — consumed by Task 5's `StudentRoute` changes.

- [ ] **Step 1: Write the failing test for the missing-field helper**

Create `batchbookui/src/test/profileCompleteness.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { computeMissingFields, hasMissingFields } from '../lib/profileCompleteness';

describe('computeMissingFields', () => {
  it('flags parentName and childEmail as missing when null', () => {
    const missing = computeMissingFields(null, { name: 'Kid', email: null });
    expect(missing).toEqual({ parentName: true, childEmail: true });
  });

  it('flags nothing missing when both are present', () => {
    const missing = computeMissingFields('Parent Name', { name: 'Kid', email: 'kid@test.com' });
    expect(missing).toEqual({ parentName: false, childEmail: false });
  });

  it('treats an absent child as childEmail missing', () => {
    const missing = computeMissingFields('Parent Name', undefined);
    expect(missing.childEmail).toBe(true);
  });
});

describe('hasMissingFields', () => {
  it('returns true when any field is missing', () => {
    expect(hasMissingFields({ parentName: false, childEmail: true })).toBe(true);
  });

  it('returns false when nothing is missing', () => {
    expect(hasMissingFields({ parentName: false, childEmail: false })).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook/batchbookui && npm run test -- profileCompleteness`
Expected: FAIL — cannot find module `../lib/profileCompleteness`

- [ ] **Step 3: Implement the helper**

Create `batchbookui/src/lib/profileCompleteness.js`:

```js
export function computeMissingFields(parentName, child) {
  return {
    parentName: !parentName,
    childEmail: !child?.email,
  };
}

export function hasMissingFields(missing) {
  return Object.values(missing).some(Boolean);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- profileCompleteness`
Expected: PASS

- [ ] **Step 5: Update `PhoneOtpStep` to pass the full verify response to `onSuccess`**

In `batchbookui/src/components/onboarding/PhoneOtpStep.jsx`, change the destructure and the `onSuccess` call inside `verifyOtp`:

```js
      const { auth_token, refresh_token, parent_name, children = [] } = await res.json();

      // Bridge the backend Supabase JWT into the Supabase JS client.
      // AuthContext will pick up the session via onAuthStateChange.
      const { error: sessionError } = await supabase.auth.setSession({
        access_token: auth_token,
        refresh_token: refresh_token,
      });
      if (sessionError) throw sessionError;

      // Stamp student role for StudentRoute guard; store child data for dashboard
      localStorage.setItem('bb_role', 'student');
      if (children.length > 0) {
        localStorage.setItem('bb_student_id', String(children[0].id));
        localStorage.setItem('bb_student_name', children[0].name ?? '');
      }

      onSuccess(phone, { parentName: parent_name, children });
```

- [ ] **Step 6: Update the existing `PhoneOtpStep` tests for the new `onSuccess` signature**

In `batchbookui/src/test/PhoneOtpStep.test.jsx`, both `global.fetch.mockResolvedValueOnce` calls for the verify step currently return `{ auth_token: 'tok', refresh_token: 'ref', children: [] }` — leave those as-is (still valid, `parent_name` just won't be in the payload, which is fine since it's destructured with no default requirement). Add one new test at the end of the `describe` block:

```js
  it('calls onSuccess with parentName and children from the verify response', async () => {
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        auth_token: 'tok',
        refresh_token: 'ref',
        parent_name: 'Priya Devi',
        children: [{ id: 1, name: 'Kid', email: null, fees_status: 'NOT_PAID' }],
      }),
    });

    const onSuccess = vi.fn();
    render(<PhoneOtpStep phone="9876543210" label="Parent's phone" onSuccess={onSuccess} />);

    await waitFor(() => expect(screen.getByLabelText(/6-digit otp/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/6-digit otp/i), { target: { value: '111111' } });
    fireEvent.click(screen.getByRole('button', { name: /verify/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith('9876543210', {
        parentName: 'Priya Devi',
        children: [{ id: 1, name: 'Kid', email: null, fees_status: 'NOT_PAID' }],
      });
    });
  });
```

- [ ] **Step 7: Run PhoneOtpStep tests to verify they pass**

Run: `npm run test -- PhoneOtpStep`
Expected: PASS

- [ ] **Step 8: Write the failing `CompleteProfileStep` test**

Create `batchbookui/src/test/CompleteProfileStep.test.jsx`:

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CompleteProfileStep from '../components/onboarding/CompleteProfileStep';

vi.mock('../services/api', () => ({
  default: { patch: vi.fn() },
}));
import api from '../services/api';

describe('CompleteProfileStep', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders only the missing fields and submits them via PATCH', async () => {
    api.patch.mockResolvedValue({ data: {} });
    const onDone = vi.fn();

    render(
      <CompleteProfileStep
        missing={{ parentName: true, childEmail: true }}
        childId={10}
        onDone={onDone}
      />
    );

    expect(screen.getByLabelText(/your name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/child's email/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Priya Devi' } });
    fireEvent.change(screen.getByLabelText(/child's email/i), { target: { value: 'kid@test.com' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith('/parent/update', { name: 'Priya Devi' });
      expect(api.patch).toHaveBeenCalledWith('/parent/children/10', { email: 'kid@test.com' });
      expect(onDone).toHaveBeenCalled();
    });
  });

  it('only renders and submits the parent name field when only that is missing', async () => {
    api.patch.mockResolvedValue({ data: {} });
    const onDone = vi.fn();

    render(
      <CompleteProfileStep
        missing={{ parentName: true, childEmail: false }}
        childId={10}
        onDone={onDone}
      />
    );

    expect(screen.getByLabelText(/your name/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/child's email/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/your name/i), { target: { value: 'Priya Devi' } });
    fireEvent.click(screen.getByRole('button', { name: /continue/i }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith('/parent/update', { name: 'Priya Devi' });
      expect(api.patch).not.toHaveBeenCalledWith('/parent/children/10', expect.anything());
      expect(onDone).toHaveBeenCalled();
    });
  });
});
```

- [ ] **Step 9: Run test to verify it fails**

Run: `npm run test -- CompleteProfileStep`
Expected: FAIL — cannot find module `../components/onboarding/CompleteProfileStep`

- [ ] **Step 10: Implement `CompleteProfileStep`**

Create `batchbookui/src/components/onboarding/CompleteProfileStep.jsx`:

```jsx
// src/components/onboarding/CompleteProfileStep.jsx
import React, { useState } from 'react';
import { Box, Typography, TextField, Button, CircularProgress } from '@mui/material';
import api from '../../services/api';

export default function CompleteProfileStep({ missing, childId, onDone }) {
  const [parentName, setParentName] = useState('');
  const [childEmail, setChildEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const canSubmit =
    (!missing.parentName || parentName.trim().length > 0) &&
    (!missing.childEmail || childEmail.trim().length > 0);

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      if (missing.parentName) {
        await api.patch('/parent/update', { name: parentName.trim() });
      }
      if (missing.childEmail) {
        await api.patch(`/parent/children/${childId}`, { email: childEmail.trim() });
      }
      onDone();
    } catch (err) {
      setError('Could not save your details: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Typography variant="h6" fontWeight={700} gutterBottom>Just one more thing</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        A couple of details are still missing from your profile.
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
        {missing.parentName && (
          <TextField
            label="Your name"
            fullWidth
            value={parentName}
            onChange={e => setParentName(e.target.value)}
            disabled={loading}
          />
        )}
        {missing.childEmail && (
          <TextField
            label="Child's email"
            fullWidth
            type="email"
            value={childEmail}
            onChange={e => setChildEmail(e.target.value)}
            disabled={loading}
          />
        )}
        {error && <Typography variant="caption" color="error">{error}</Typography>}
        <Button
          variant="contained"
          color="primary"
          fullWidth
          size="large"
          disabled={loading || !canSubmit}
          onClick={handleSubmit}
          sx={{ py: 1.5, borderRadius: 2, fontWeight: 700 }}
        >
          {loading ? <CircularProgress size={22} color="inherit"/> : 'Continue'}
        </Button>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 11: Run test to verify it passes**

Run: `npm run test -- CompleteProfileStep`
Expected: PASS

- [ ] **Step 12: Simplify `OnboardingWizard` for the student role and wire the missing-field redirect**

In `batchbookui/src/components/onboarding/OnboardingWizard.jsx`:

Replace the `STEPS` constant:

```js
const STEPS = {
  student: ['role', 'parentOtp'],
  teacher: ['role', 'profile', 'institution', 'teacherOtp'],
};
```

Remove the `ParentDetailsStep` import (`import ParentDetailsStep from './ParentDetailsStep';`) and add:

```js
import { computeMissingFields, hasMissingFields } from '../../lib/profileCompleteness';
```

Replace `validateStep`, `next`, and `handleOtpSuccess`:

```js
  const validateStep = () => {
    const e = {};
    if (currentStepId === 'role' && !data.role) { e.role = 'Please select a role.'; }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const next = () => {
    if (data.role === 'owner') {
      navigate('/phone-login');
      return;
    }
    if (validateStep()) setStep(s => s + 1);
  };
  const back = () => { setErrors({}); setStep(s => s - 1); };
  const skip = () => setStep(s => s + 1);

  const handleOtpSuccess = (phone, { parentName, children } = {}) => {
    const primaryChild = children?.[0];
    const missing = computeMissingFields(parentName, primaryChild);
    if (primaryChild && hasMissingFields(missing)) {
      navigate('/complete-profile', { state: { missing, childId: primaryChild.id } });
      return;
    }
    navigate('/dashboard/student');
  };
```

Update `renderStep()` — remove the `case 'parentDetails':` branch and change the `case 'parentOtp':` branch:

```js
      case 'parentOtp':
        return <PhoneOtpStep label="Parent's mobile number" onSuccess={handleOtpSuccess}/>;
```

Update the footer button label — the `'parentDetails'` branch it checked for no longer exists, so replace the conditional with the plain literal. Find:

```jsx
            >
              {currentStepId === 'parentDetails' ? 'Send OTP to Parent' : 'Continue'}
            </Button>
```

Replace with:

```jsx
            >
              Continue
            </Button>
```

- [ ] **Step 13: Delete the now-unreachable `ParentDetailsStep`**

```bash
git rm batchbookui/src/components/onboarding/ParentDetailsStep.jsx
```

- [ ] **Step 14: Register the `/complete-profile` route**

In `batchbookui/src/App.jsx`, add the import:

```js
import CompleteProfileStep from './components/onboarding/CompleteProfileStep';
```

Add a small wrapper route component right after the `OnboardingWizard` import block (this reads the `location.state` set by `navigate('/complete-profile', { state: {...} })` in Step 12, and by `StudentRoute` in Task 5):

```jsx
function CompleteProfilePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { missing, childId } = location.state || {};
  if (!missing) return <Navigate to="/dashboard/student" replace />;
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', bgcolor: 'background.default', p: 2 }}>
      <Box sx={{ width: '100%', maxWidth: 460, p: 4, borderRadius: 4, boxShadow: 3, bgcolor: 'background.paper' }}>
        <CompleteProfileStep
          missing={missing}
          childId={childId}
          onDone={() => navigate('/dashboard/student', { replace: true })}
        />
      </Box>
    </Box>
  );
}
```

Add `useLocation, useNavigate` to the `react-router-dom` import at the top of `App.jsx`:

```js
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
```

Add the route inside `<Routes>`, next to the student dashboard route:

```jsx
            <Route
              path="/complete-profile"
              element={<StudentRoute><CompleteProfilePage /></StudentRoute>}
            />
```

- [ ] **Step 15: Manually verify the website flow**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && make dev` (or `cd batchbookui && npm run dev` if the backend is already running separately)

In a browser at `http://localhost:5173/onboarding`: pick "Student", confirm you land straight on a phone-number entry screen (no name/parent-name form), enter a phone number already seeded with a linked child but no parent name (e.g. reuse the Play Store reviewer number `9999999998` if its parent name is null, or seed one via `POST /admin/seed-demo-accounts`), verify OTP, and confirm you land on `/complete-profile` with only the actually-missing fields shown, then land on `/dashboard/student` after submitting.

- [ ] **Step 16: Run the full website test suite**

Run: `npm run test`
Expected: PASS, all tests.

- [ ] **Step 17: Commit inside the `batchbookui` submodule, then bump the pointer**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook/batchbookui
git add src/lib/profileCompleteness.js src/components/onboarding/CompleteProfileStep.jsx \
  src/components/onboarding/OnboardingWizard.jsx src/components/onboarding/PhoneOtpStep.jsx \
  src/App.jsx src/test/profileCompleteness.test.js src/test/CompleteProfileStep.test.jsx \
  src/test/PhoneOtpStep.test.jsx
git rm src/components/onboarding/ParentDetailsStep.jsx
git commit -m "feat: phone/OTP-first student onboarding with post-verify missing-field step"
git push origin master

cd /Users/bedantsharma/PycharmProjects/BatchBook
git add batchbookui
git commit -m "chore: bump batchbookui submodule to latest"
```

(Confirm the submodule's default branch name with `cd batchbookui && git branch --show-current` before pushing if it isn't `master`.)

---

## Task 5: Website — `StudentRoute` session-restore fallback

**Files:**
- Modify: `batchbookui/src/components/StudentRoute.jsx`
- Test: `batchbookui/src/test/StudentRoute.test.jsx`

**Interfaces:**
- Consumes: `computeMissingFields`/`hasMissingFields` from Task 4's `profileCompleteness.js`; `api` axios instance (`GET /parent/me`); `useAuth()` from `AuthContext`.

- [ ] **Step 1: Write the failing test**

Create `batchbookui/src/test/StudentRoute.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import StudentRoute from '../components/StudentRoute';

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ session: { access_token: 'tok' }, loading: false }),
}));

vi.mock('../services/api', () => ({
  default: { get: vi.fn() },
}));
import api from '../services/api';

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={['/dashboard/student']}>
      <Routes>
        <Route path="/dashboard/student" element={<StudentRoute><div>Dashboard</div></StudentRoute>} />
        <Route path="/complete-profile" element={<div>Complete profile page</div>} />
        <Route path="/onboarding" element={<div>Onboarding page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('StudentRoute — session-restore fallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('restores role via /parent/me and renders the guarded page when profile is complete', async () => {
    api.get.mockResolvedValue({
      data: { id: 1, name: 'Priya', phone_number: '9876543210', children: [{ id: 10, name: 'Kid', email: 'kid@test.com' }] },
    });

    renderGuarded();

    await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument());
    expect(localStorage.getItem('bb_role')).toBe('student');
    expect(localStorage.getItem('bb_student_id')).toBe('10');
  });

  it('redirects to /complete-profile when the restored profile is missing fields', async () => {
    api.get.mockResolvedValue({
      data: { id: 1, name: null, phone_number: '9876543210', children: [{ id: 10, name: 'Kid', email: null }] },
    });

    renderGuarded();

    await waitFor(() => expect(screen.getByText('Complete profile page')).toBeInTheDocument());
  });

  it('falls back to /onboarding when /parent/me fails', async () => {
    api.get.mockRejectedValue(new Error('401'));

    renderGuarded();

    await waitFor(() => expect(screen.getByText('Onboarding page')).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- StudentRoute`
Expected: FAIL — current `StudentRoute` redirects to `/onboarding` immediately in all three cases (no `/parent/me` call happens).

- [ ] **Step 3: Implement the fallback**

Replace the full contents of `batchbookui/src/components/StudentRoute.jsx`:

```jsx
import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Box, CircularProgress } from '@mui/material';
import api from '../services/api';
import { computeMissingFields, hasMissingFields } from '../lib/profileCompleteness';

/**
 * StudentRoute — guards any route that requires an authenticated student/parent.
 *
 * Fast path: `bb_role === 'student'` in localStorage + a live session — renders
 * immediately, no network call.
 *
 * Fallback: a live session exists but `bb_role` is missing (cleared storage, new
 * device) — call GET /parent/me to restore the role instead of forcing the whole
 * onboarding flow again. If that profile is missing fields, redirect to
 * /complete-profile instead of the originally-requested page.
 */
export default function StudentRoute({ children }) {
  const { session, loading } = useAuth();
  const location = useLocation();
  const role = localStorage.getItem('bb_role');
  const [restoring, setRestoring] = useState(session && role !== 'student');
  const [restoreResult, setRestoreResult] = useState(null); // 'ok' | 'incomplete' | 'failed' | null

  useEffect(() => {
    if (loading || !session || role === 'student') return;
    let cancelled = false;
    setRestoring(true);
    api.get('/parent/me')
      .then(({ data }) => {
        if (cancelled) return;
        localStorage.setItem('bb_role', 'student');
        const child = data.children?.[0];
        if (child) {
          localStorage.setItem('bb_student_id', String(child.id));
          localStorage.setItem('bb_student_name', child.name ?? '');
        }
        const missing = computeMissingFields(data.name, child);
        if (child && hasMissingFields(missing)) {
          setRestoreResult({ status: 'incomplete', missing, childId: child.id });
        } else {
          setRestoreResult({ status: 'ok' });
        }
      })
      .catch(() => { if (!cancelled) setRestoreResult({ status: 'failed' }); })
      .finally(() => { if (!cancelled) setRestoring(false); });
    return () => { cancelled = true; };
  }, [loading, session, role]);

  if (loading || restoring) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          bgcolor: 'background.default',
        }}
      >
        <CircularProgress color="primary" />
      </Box>
    );
  }

  if (!session) {
    return <Navigate to="/onboarding" replace />;
  }

  if (role === 'student') {
    return children;
  }

  if (restoreResult?.status === 'ok') {
    return children;
  }
  if (restoreResult?.status === 'incomplete') {
    if (location.pathname === '/complete-profile') return children;
    return (
      <Navigate
        to="/complete-profile"
        state={{ missing: restoreResult.missing, childId: restoreResult.childId }}
        replace
      />
    );
  }

  return <Navigate to="/onboarding" replace />;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test -- StudentRoute`
Expected: PASS

- [ ] **Step 5: Run the full website test suite**

Run: `npm run test`
Expected: PASS, all tests.

- [ ] **Step 6: Manually verify the restore path**

With the site running and logged in as a student, open devtools and run `localStorage.removeItem('bb_role')`, then reload `/dashboard/student` directly. Confirm it briefly shows the loading spinner, then either lands back on the dashboard (profile complete) or on `/complete-profile` (profile incomplete) — not `/onboarding`.

- [ ] **Step 7: Commit inside the `batchbookui` submodule, then bump the pointer**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook/batchbookui
git add src/components/StudentRoute.jsx src/test/StudentRoute.test.jsx
git commit -m "feat: restore student session via /parent/me when cached role is missing"
git push origin master

cd /Users/bedantsharma/PycharmProjects/BatchBook
git add batchbookui
git commit -m "chore: bump batchbookui submodule to latest"
```

---

## Task 6: Manual end-to-end QA pass

**Files:** none (verification only)

- [ ] **Step 1: Seed a test account with an incomplete profile**

Run against the local backend: `curl -X POST http://localhost:8000/admin/seed-demo-accounts -H "X-Admin-Secret: $ADMIN_BACKFILL_SECRET"` — confirms the parent+student exist. If the seeded parent already has a name, manually null it out via `psql`/Supabase dashboard for this test, or invite a fresh student via the owner UI without a parent name.

- [ ] **Step 2: Fully-complete returning parent — website**

Log in with a phone number whose parent name and child email are both already set. Confirm: phone entry → OTP → straight to `/dashboard/student`, no `CompleteProfileStep` screen shown.

- [ ] **Step 3: Incomplete profile — website**

Log in with the phone number from Step 1 (missing parent name). Confirm: phone entry → OTP → `/complete-profile` showing only the parent-name field (not a child-email field, if the child's email is already set) → submit → `/dashboard/student`.

- [ ] **Step 4: Zero-children blocker — website**

Attempt phone/OTP verification with a phone number that has never been invited by any tutor. Confirm the existing "ask your tutor to add you first"-equivalent behavior on the website is unchanged (check `PhoneOtpStep`'s error handling — it currently surfaces the backend's error message directly since `children.length === 0` isn't special-cased client-side the way the mobile app does it; confirm this still reads sensibly, and if not, note it as a follow-up rather than silently changing scope here).

- [ ] **Step 5: Session-restore fallback — website**

Per Task 5 Step 6.

- [ ] **Step 6: Confirm the WhatsApp `enrollment_invite` link lands on the new flow correctly**

Find where the invite link URL is built for the `enrollment_invite` WhatsApp template (search `services/` for the notification/dispatch call inside `EnrollmentService.invite_student`, likely a `services/notification_service.py` or similar templating call). Confirm what URL/deep-link it sends the parent. If it's just the website's root/landing URL, no change is needed — the parent taps it, picks "Student", and lands on the same phone→OTP→missing-check path as Task 4. If it deep-links to a since-removed route (e.g. anything pointing at the old `/onboarding` flow expecting `parentDetails` step state), update the link target or the route so it resolves correctly — this is a discovery step, not a pre-decided change; if the link already resolves fine, note that and move on.

- [ ] **Step 7: Backend — run the full suite once more**

Run: `cd /Users/bedantsharma/PycharmProjects/BatchBook && uv run pytest -v`
Expected: PASS, all tests, confirming Tasks 1–3 didn't regress anything seeded/exercised by Tasks 4–5's manual QA.
