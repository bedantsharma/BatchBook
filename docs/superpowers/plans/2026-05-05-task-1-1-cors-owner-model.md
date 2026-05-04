# Task 1.1 — CORS + Owner Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add CORS middleware to the FastAPI app, create the Owner model with OTP-based auth, and expose 4 owner endpoints mirroring the student auth pattern.

**Architecture:** Owner auth mirrors the student auth flow exactly — OTP via Supabase, JWT returned, all subsequent requests validated against Supabase. The shared `get_current_user_id` logic is extracted into `services/auth_service.py` so neither student nor owner service duplicates it. No test infrastructure exists yet (deferred to Phase 6); verification is done via FastAPI `/docs`.

**Tech Stack:** FastAPI, SQLAlchemy async, Supabase AsyncClient, Pydantic v2, Alembic, loguru

---

### Task 1: Add CORS middleware to `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add CORSMiddleware import and middleware registration**

Open `app.py` and add the middleware after the `app = FastAPI(...)` block:

```python
from fastapi.middleware.cors import CORSMiddleware

# after app = FastAPI(...)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Verify the server still starts**

```bash
cd ~/PycharmProjects/BatchBook
source .venv/bin/activate
uvicorn app:app --reload --port 8000
```

Expected: Server starts, no import errors, `GET /docs` returns 200.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add CORS middleware for localhost:5173"
```

---

### Task 2: Extract shared auth utility into `services/auth_service.py`

**Files:**
- Create: `services/auth_service.py`
- Modify: `services/student_service.py`

The `get_current_user_id` method in `StudentService` is about to be needed by `OwnerService` too. Extract it now so both services use the same code path.

- [ ] **Step 1: Create `services/auth_service.py`**

```python
from uuid import UUID

from supabase import AsyncClient


async def get_current_user_id(supabase: AsyncClient, authorization: str) -> UUID:
    token = authorization.removeprefix("Bearer ").strip()
    response = await supabase.auth.get_user(token)
    return UUID(str(response.user.id))
```

- [ ] **Step 2: Update `services/student_service.py` to delegate to the shared util**

Replace the `get_current_user_id` method body in `StudentService`:

```python
from services.auth_service import get_current_user_id as _get_user_id

# inside StudentService class, replace the method:
async def get_current_user_id(self, supabase: AsyncClient, authorization: str) -> UUID:
    return await _get_user_id(supabase, authorization)
```

Add the import at the top of `student_service.py`:
```python
from supabase import AsyncClient
```
(if not already present — check first)

- [ ] **Step 3: Restart the server and verify `/student/me` still works via `/docs`**

Hit `GET /student/me` with a valid Bearer token. Expected: 200 with student profile (same as before).

- [ ] **Step 4: Commit**

```bash
git add services/auth_service.py services/student_service.py
git commit -m "refactor: extract get_current_user_id into shared auth_service"
```

---

### Task 3: Create the Owner SQLAlchemy model

**Files:**
- Create: `models/owner_base.py`

- [ ] **Step 1: Create `models/owner_base.py`**

```python
from datetime import datetime

from sqlalchemy import UUID, Column, DateTime, Integer, String

from db.base import Base


class OwnerSchema(Base):
    __tablename__ = "Owner"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=True)
    phone_number = Column(String, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=False)
    institute_name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
```

- [ ] **Step 2: Commit**

```bash
git add models/owner_base.py
git commit -m "feat: add OwnerSchema SQLAlchemy model"
```

---

### Task 4: Create and run Alembic migration for the Owner table

**Files:**
- Creates: `alembic/versions/<hash>_add_owner_table.py` (auto-generated)

The Alembic `env.py` must import the new model so autogenerate can see it.

- [ ] **Step 1: Check `alembic/env.py` to see how models are imported**

```bash
cat alembic/env.py
```

Look for the `target_metadata` line and how existing models are imported. You need to add an import for `OwnerSchema`.

- [ ] **Step 2: Add `OwnerSchema` import to `alembic/env.py`**

Find the block where models are imported (look for `from models.student_base import StudentSchema` or similar). Add:

```python
from models.owner_base import OwnerSchema  # noqa: F401
```

- [ ] **Step 3: Generate the migration**

```bash
cd ~/PycharmProjects/BatchBook
source .venv/bin/activate
alembic revision --autogenerate -m "add owner table"
```

Expected: A new file appears in `alembic/versions/` with an `op.create_table("Owner", ...)` call.

- [ ] **Step 4: Inspect the generated migration**

```bash
cat alembic/versions/*add_owner_table*.py
```

Verify it has `op.create_table("Owner", ...)` with the correct columns. If it's empty or wrong, check that `OwnerSchema` was imported in `env.py`.

- [ ] **Step 5: Run the migration**

```bash
alembic upgrade head
```

Expected: No errors. The `Owner` table now exists in your Supabase/PostgreSQL database.

- [ ] **Step 6: Commit**

```bash
git add alembic/env.py alembic/versions/
git commit -m "feat: alembic migration — add Owner table"
```

---

### Task 5: Create `repositories/owner_repository.py`

**Files:**
- Create: `repositories/owner_repository.py`

- [ ] **Step 1: Create `repositories/owner_repository.py`**

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.owner_base import OwnerSchema


class OwnerRepository:
    async def create_owner(self, db: AsyncSession, owner: OwnerSchema) -> OwnerSchema:
        db.add(owner)
        await db.commit()
        await db.refresh(owner)
        return owner

    async def get_by_user_id(self, db: AsyncSession, user_id: UUID) -> OwnerSchema | None:
        result = await db.execute(
            select(OwnerSchema).where(OwnerSchema.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, db: AsyncSession, phone: str) -> OwnerSchema | None:
        result = await db.execute(
            select(OwnerSchema).where(OwnerSchema.phone_number == phone)
        )
        return result.scalar_one_or_none()

    async def update_owner(
        self, db: AsyncSession, owner: OwnerSchema, updates: dict
    ) -> OwnerSchema:
        for key, value in updates.items():
            setattr(owner, key, value)
        await db.commit()
        await db.refresh(owner)
        return owner
```

- [ ] **Step 2: Commit**

```bash
git add repositories/owner_repository.py
git commit -m "feat: add OwnerRepository with CRUD methods"
```

---

### Task 6: Create Owner Pydantic DTOs

**Files:**
- Create: `DTO/owner_model.py`
- Create: `routes/requests/owner_verify_otp_request.py`
- Create: `routes/requests/update_owner_request.py`
- Create: `routes/responses/owner_profile_response.py`
- Create: `routes/responses/verify_owner_response.py`

- [ ] **Step 1: Create `DTO/owner_model.py`**

```python
from pydantic import BaseModel, Field


class Owner(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone_number: str = Field(min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
    institute_name: str | None = None
    city: str | None = None
```

- [ ] **Step 2: Create `routes/requests/owner_verify_otp_request.py`**

```python
from pydantic import BaseModel, Field


class OwnerVerifyOtpRequest(BaseModel):
    token: str
    phone: str = Field(min_length=10, max_length=10, pattern=r"^[6-9]\d{9}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
```

- [ ] **Step 3: Create `routes/requests/update_owner_request.py`**

```python
from pydantic import BaseModel


class UpdateOwnerRequest(BaseModel):
    name: str | None = None
    institute_name: str | None = None
    city: str | None = None
```

- [ ] **Step 4: Create `routes/responses/owner_profile_response.py`**

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OwnerProfileResponse(BaseModel):
    id: int
    name: str | None
    phone_number: str
    institute_name: str | None
    city: str | None
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Create `routes/responses/verify_owner_response.py`**

```python
from pydantic import BaseModel, Field


class VerifyOwnerResponse(BaseModel):
    auth_token: str = Field(min_length=10)
    aud: str = Field(...)
    user_id: str = Field(...)
```

- [ ] **Step 6: Commit**

```bash
git add DTO/owner_model.py routes/requests/owner_verify_otp_request.py routes/requests/update_owner_request.py routes/responses/owner_profile_response.py routes/responses/verify_owner_response.py
git commit -m "feat: add Owner DTOs, request/response models"
```

---

### Task 7: Create `services/owner_service.py`

**Files:**
- Create: `services/owner_service.py`

- [ ] **Step 1: Create `services/owner_service.py`**

```python
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from models.owner_base import OwnerSchema
from repositories.owner_repository import OwnerRepository
from services.auth_service import get_current_user_id


class OwnerService:
    def __init__(self):
        self.owner_repo = OwnerRepository()

    async def get_or_create_after_otp(
        self,
        db: AsyncSession,
        user_id: UUID,
        phone: str,
        name: str | None,
    ) -> OwnerSchema:
        existing = await self.owner_repo.get_by_user_id(db, user_id)
        if existing:
            return existing
        owner = OwnerSchema(user_id=user_id, phone_number=phone, name=name)
        return await self.owner_repo.create_owner(db, owner)

    async def verify_otp(
        self,
        supabase: AsyncClient,
        db: AsyncSession,
        phone: str,
        token: str,
        name: str | None,
    ) -> tuple[str, str, UUID]:
        data = await supabase.auth.verify_otp({
            "phone": f"+91{phone}",
            "token": token,
            "type": "sms",
        })
        if not data.user or not data.session:
            raise ValueError("OTP verification failed")
        user_id = UUID(str(data.user.id))
        await self.get_or_create_after_otp(db, user_id, phone, name)
        return data.session.access_token, data.user.aud, user_id

    async def get_current_user_id(self, supabase: AsyncClient, authorization: str) -> UUID:
        return await get_current_user_id(supabase, authorization)

    async def get_owner_by_user_id(
        self, db: AsyncSession, user_id: UUID
    ) -> OwnerSchema | None:
        return await self.owner_repo.get_by_user_id(db, user_id)

    async def update_owner(
        self, db: AsyncSession, user_id: UUID, updates: dict
    ) -> OwnerSchema | None:
        owner = await self.owner_repo.get_by_user_id(db, user_id)
        if not owner:
            return None
        return await self.owner_repo.update_owner(db, owner, updates)


def get_owner_service() -> OwnerService:
    return OwnerService()
```

- [ ] **Step 2: Commit**

```bash
git add services/owner_service.py
git commit -m "feat: add OwnerService with OTP verify and profile methods"
```

---

### Task 8: Create `routes/owner_route.py` and register it

**Files:**
- Create: `routes/owner_route.py`
- Modify: `app.py`

- [ ] **Step 1: Create `routes/owner_route.py`**

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from clients.supabase_client import get_supabase_client
from db.session import get_db
from services.owner_service import OwnerService, get_owner_service
from routes.requests.otp_generate_request import OtpGenerateRequest
from routes.requests.owner_verify_otp_request import OwnerVerifyOtpRequest
from routes.requests.update_owner_request import UpdateOwnerRequest
from routes.responses.owner_profile_response import OwnerProfileResponse
from routes.responses.verify_owner_response import VerifyOwnerResponse

router = APIRouter(prefix="/owner")

SupabaseClient = Annotated[AsyncClient, Depends(get_supabase_client)]
OwnerServiceDep = Annotated[OwnerService, Depends(get_owner_service)]


async def _get_current_owner_id(
    authorization: Annotated[str, Header()],
    supabase: SupabaseClient,
    owner_service: OwnerServiceDep,
) -> UUID:
    try:
        return await owner_service.get_current_user_id(supabase, authorization)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post(
    "/generate_otp",
    summary="Send an OTP to the given Indian mobile number (owner login)",
)
async def send_otp(request: OtpGenerateRequest, supabase: SupabaseClient):
    try:
        return await supabase.auth.sign_in_with_otp({"phone": f"+91{request.phone}"})
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )


@router.post(
    "/verify_otp",
    summary="Verify OTP and upsert owner record; returns a JWT",
    response_model=VerifyOwnerResponse,
)
async def verify_otp(
    verify_request: OwnerVerifyOtpRequest,
    owner_service: OwnerServiceDep,
    supabase: SupabaseClient,
    db: AsyncSession = Depends(get_db),
):
    try:
        access_token, aud, user_id = await owner_service.verify_otp(
            supabase=supabase,
            db=db,
            phone=verify_request.phone,
            token=verify_request.token,
            name=verify_request.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500,
            detail="Could not communicate with Supabase server — check logs",
        )
    return VerifyOwnerResponse(auth_token=access_token, aud=aud, user_id=str(user_id))


@router.get(
    "/me",
    summary="Fetch the authenticated owner's profile",
    response_model=OwnerProfileResponse,
)
async def get_owner(
    owner_service: OwnerServiceDep,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(_get_current_owner_id),
):
    owner = await owner_service.get_owner_by_user_id(db=db, user_id=user_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    return owner


@router.patch(
    "/update",
    summary="Update the authenticated owner's profile (name, institute_name, city)",
    response_model=OwnerProfileResponse,
)
async def update_owner(
    update_request: UpdateOwnerRequest,
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    user_id: UUID = Depends(_get_current_owner_id),
):
    updates = update_request.model_dump(exclude_none=True)
    updated = await owner_service.update_owner(db=db, user_id=user_id, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Owner record not found")
    return updated
```

- [ ] **Step 2: Register the owner router in `app.py`**

Add to `app.py` (after existing student router import and registration):

```python
from routes.owner_route import router as owner_router

# after app.include_router(router=student_router)
app.include_router(router=owner_router)
```

- [ ] **Step 3: Restart server and verify**

```bash
uvicorn app:app --reload --port 8000
```

Open `http://localhost:8000/docs` — you should see 4 new endpoints under the `/owner` section:
- `POST /owner/generate_otp`
- `POST /owner/verify_otp`
- `GET /owner/me`
- `PATCH /owner/update`

- [ ] **Step 4: Smoke test via `/docs`**

1. Hit `POST /owner/generate_otp` with your phone number → SMS OTP arrives
2. Hit `POST /owner/verify_otp` with phone + OTP token → get back `auth_token`
3. Hit `GET /owner/me` with `Authorization: Bearer <auth_token>` → get back owner profile
4. Hit `PATCH /owner/update` with `{ "institute_name": "Test Classes", "city": "Delhi" }` → profile updated

- [ ] **Step 5: Commit**

```bash
git add routes/owner_route.py app.py
git commit -m "feat: add owner routes (generate_otp, verify_otp, me, update) and register router"
```

---

## Self-Review

**Spec coverage check:**
- ✅ CORS added to `app.py` (Task 1)
- ✅ `get_current_user_id` extracted to `auth_service.py` (Task 2)
- ✅ `OwnerSchema` model with all required fields (Task 3)
- ✅ Alembic migration created and applied (Task 4)
- ✅ `OwnerRepository` with 4 functions: `create_owner`, `get_by_user_id`, `get_by_phone`, `update_owner` (Task 5)
- ✅ Owner DTOs, request/response models (Task 6)
- ✅ `OwnerService` with OTP logic and `get_owner_service` factory (Task 7)
- ✅ 4 endpoints in `owner_route.py`, router registered in `app.py` (Task 8)
- ✅ Smoke test via `/docs` (Task 8, Step 4)

**Gaps:** None — all roadmap items for Task 1.1 are covered. Task 1.2 (Institute model) is a separate task in the roadmap and not included here intentionally.
