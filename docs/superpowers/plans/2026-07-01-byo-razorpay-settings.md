# BYO-Razorpay Settings Page (Phase F, Task F.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Do not `git push` or `gh pr create` without explicit user confirmation first** — those are visible/shared-state actions. Everything else (local commits on the feature branches) is fine to run autonomously.

**Goal:** Let each owner store their own Razorpay Key ID/Secret on their `Institute` row (secret encrypted at rest) via a new "Settings → Payouts" page in the owner dashboard, with a connection-status banner surfaced on the Fees page. This is Task F.1 from `BATCHBOOK_ROADMAP_V2.md` — schema + UI only. It does **not** include: rejecting `rzp_test_` keys, a live Razorpay validation ping, or switching `fee_service.generate_payment_link()` to use the per-institute client (those are Tasks F.2/F.3, separate follow-up plans).

**Architecture:** Backend adds three nullable columns to `Institute` (`razorpay_key_id`, `razorpay_key_secret_encrypted`, `razorpay_status`) plus a small Fernet-based encryption utility, one new service method, and two new routes (`GET`/`PATCH /owner/institute/payouts`). Frontend adds a `SettingsPage.jsx` owner-dashboard section and a dismissible "Connect Payouts" banner on `FeesPage.jsx`.

**Simplification vs. the roadmap's step 3 ("trigger is lazy... appears when owner clicks Generate Payment Link"):** the owner-facing frontend has no "Generate Payment Link" button today (only the student dashboard's "Pay Now" calls that endpoint). So the banner shows on every Fees page visit when payouts aren't connected, with a per-visit dismiss (×) rather than being gated on a click that doesn't exist yet. Revisit if/when an owner-side payment-link button is added.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, `cryptography` (Fernet), pytest/pytest-asyncio (backend); React 19, MUI 9, Vitest 4 + @testing-library/react (frontend).

## Global Constraints

- Backend package manager: `uv` — use `uv add <pkg>` / `uv run <cmd>`, never bare `pip`/`python`.
- Backend linter: `ruff`, line length 100, Python 3.14 target.
- Backend tests: `uv run pytest -v` from `/Users/bedantsharma/PycharmProjects/BatchBook`.
- Backend work happens on git branch `feat/byo-razorpay-payouts` (already created in the parent `BatchBook` repo — do not create a new one).
- `batchbookui/` is a **separate git submodule repo**. Frontend work happens on a new branch `feat/byo-razorpay-settings-ui` created *inside* `batchbookui/`. Commit there with its own `git commit`; never `git add batchbookui/` (trailing slash) from the parent repo — only `git add batchbookui` (no slash) to bump the pointer, and only in the final task.
- Frontend package manager: `npm`. Tests: `npm test` (runs `vitest run`) from `batchbookui/`.
- Never return `razorpay_key_secret` (plaintext or encrypted) in any API response — only a `secret_configured: bool`.
- Follow the existing repo pattern: `str, enum.Enum` Python enums stored via SQLAlchemy `Enum()`, and Alembic migrations hand-written to match `alembic/versions/h2i3j4k5l6m7_institute_join_code_parent_institute.py` and `00f800b106b9_add_notification_table.py` in style (autogenerate needs a live DB connection to Supabase and isn't used for hand-added enum-typed columns in this repo's convention).

---

## File Map

| File | Change |
|------|--------|
| `pyproject.toml` | Add `cryptography` dependency |
| `config.py` | Add `razorpay_encryption_key: str \| None = None` |
| `services/crypto_service.py` | Create — `encrypt_secret()` / `decrypt_secret()` (Fernet) |
| `tests/test_crypto_service.py` | Create — round-trip + bad-token tests |
| `tests/conftest.py` | Add `RAZORPAY_ENCRYPTION_KEY` test default |
| `models/institute_base.py` | Add `RazorpayStatus` enum + 3 columns |
| `alembic/versions/i3j4k5l6m7n8_institute_razorpay_payout_fields.py` | Create — migration |
| `services/institute_service.py` | Add `connect_razorpay()` method |
| `tests/test_institute_service.py` | Add tests for `connect_razorpay()` |
| `routes/requests/update_razorpay_credentials_request.py` | Create |
| `routes/responses/razorpay_payout_response.py` | Create |
| `routes/owner_route.py` | Add `GET`/`PATCH /owner/institute/payouts` |
| `tests/test_institute_routes.py` | Add route tests |
| `batchbookui/src/services/ownerService.js` | Add `getRazorpayPayoutStatus()` / `saveRazorpayCredentials()` |
| `batchbookui/src/pages/owner/SettingsPage.jsx` | Create |
| `batchbookui/src/pages/owner/OwnerDashboard.jsx` | Add `settings` nav item + `MainContent` case; pass `onNavigateToSettings` to `FeesPage` |
| `batchbookui/src/pages/owner/FeesPage.jsx` | Add "Connect Payouts" banner |
| `batchbookui/src/test/SettingsPage.test.jsx` | Create |
| `batchbookui/src/test/FeesPage.test.jsx` | Add banner tests |

---

## Task 1: Encryption utility for the Razorpay secret

**Files:**
- Modify: `pyproject.toml`
- Modify: `config.py`
- Modify: `tests/conftest.py`
- Create: `services/crypto_service.py`
- Create: `tests/test_crypto_service.py`

**Interfaces:**
- Produces: `encrypt_secret(plaintext: str) -> str`, `decrypt_secret(token: str) -> str` in `services/crypto_service.py`. Later tasks import these from `services.crypto_service`.

- [ ] **Step 1: Add the `cryptography` dependency**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
uv add cryptography
```

Expected: `pyproject.toml` gains a `cryptography>=...` line under `dependencies`.

- [ ] **Step 2: Add the config field**

In `config.py`, add one line inside `class Settings(BaseSettings)`, right after `razorpay_key_secret`:

```python
    razorpay_key_secret: str | None = None
    razorpay_encryption_key: str | None = None
```

- [ ] **Step 3: Add a test-only encryption key to conftest**

In `tests/conftest.py`, add a line right after the existing `os.environ.setdefault("RATE_LIMIT_ENABLED", "false")`:

```python
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("RAZORPAY_ENCRYPTION_KEY", "T-y7CuMZv82GDX0nnga1eU-Y4mfdPg34fVdzJv1QQ70=")
```

(This is a fixed, non-secret Fernet key used only in the test suite — generated once via `Fernet.generate_key()`.)

- [ ] **Step 4: Write the failing test**

Create `tests/test_crypto_service.py`:

```python
import pytest

from services.crypto_service import decrypt_secret, encrypt_secret


def test_encrypt_then_decrypt_round_trips():
    plaintext = "rzp_live_abcdef123456"
    encrypted = encrypt_secret(plaintext)
    assert encrypted != plaintext
    assert decrypt_secret(encrypted) == plaintext


def test_decrypt_garbage_raises_value_error():
    with pytest.raises(ValueError):
        decrypt_secret("not-a-valid-fernet-token")
```

- [ ] **Step 5: Run the test to verify it fails**

```bash
uv run pytest tests/test_crypto_service.py -v
```

Expected: FAIL / ERROR — `services.crypto_service` does not exist yet.

- [ ] **Step 6: Implement `services/crypto_service.py`**

```python
from cryptography.fernet import Fernet, InvalidToken

from config import get_settings


class EncryptionNotConfigured(RuntimeError):
    """Raised when RAZORPAY_ENCRYPTION_KEY is not set."""


def _get_fernet() -> Fernet:
    settings = get_settings()
    if not settings.razorpay_encryption_key:
        raise EncryptionNotConfigured(
            "RAZORPAY_ENCRYPTION_KEY not set — generate one with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"` and add it to .env'
        )
    return Fernet(settings.razorpay_encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext Razorpay key secret for storage at rest."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a stored Razorpay key secret.

    Raises:
        ValueError: If the token is malformed or was encrypted with a
            different key (key rotation, corruption).
    """
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Could not decrypt stored secret — key may have changed") from e
```

- [ ] **Step 7: Run the test to verify it passes**

```bash
uv run pytest tests/test_crypto_service.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock config.py tests/conftest.py services/crypto_service.py tests/test_crypto_service.py
git commit -m "feat(payouts): add Fernet-based encryption utility for Razorpay secrets"
```

---

## Task 2: `Institute` schema fields + migration

**Files:**
- Modify: `models/institute_base.py`
- Create: `alembic/versions/i3j4k5l6m7n8_institute_razorpay_payout_fields.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `RazorpayStatus` enum (`NOT_CONNECTED`, `CONNECTED`, `NEEDS_RECONNECT`) exported from `models.institute_base`; `InstituteSchema.razorpay_key_id: str | None`, `.razorpay_key_secret_encrypted: str | None`, `.razorpay_status: RazorpayStatus`. Task 3 imports `RazorpayStatus` from here.

- [ ] **Step 1: Update the model**

Replace the full contents of `models/institute_base.py`:

```python
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String

from db.base import Base


class RazorpayStatus(str, enum.Enum):
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTED = "CONNECTED"
    NEEDS_RECONNECT = "NEEDS_RECONNECT"


class InstituteSchema(Base):
    __tablename__ = "Institute"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("Owner.id"), nullable=False, unique=True)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    join_code = Column(String(8), nullable=False, unique=True, index=True)
    razorpay_key_id = Column(String, nullable=True)
    razorpay_key_secret_encrypted = Column(String, nullable=True)
    razorpay_status = Column(Enum(RazorpayStatus), nullable=False, default=RazorpayStatus.NOT_CONNECTED)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
```

- [ ] **Step 2: Write the migration**

Create `alembic/versions/i3j4k5l6m7n8_institute_razorpay_payout_fields.py`:

```python
"""institute razorpay payout fields

Revision ID: i3j4k5l6m7n8
Revises: 00f800b106b9
Create Date: 2026-07-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "i3j4k5l6m7n8"
down_revision: str | Sequence[str] | None = "00f800b106b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAZORPAY_STATUS_VALUES = ("NOT_CONNECTED", "CONNECTED", "NEEDS_RECONNECT")


def upgrade() -> None:
    # ALTER TABLE ADD COLUMN does not auto-emit CREATE TYPE the way CREATE TABLE
    # does, so the enum type must be created explicitly first. The column then
    # references the same type with create_type=False so add_column's DDL
    # compilation doesn't try (and fail) to create it a second time.
    postgresql.ENUM(*RAZORPAY_STATUS_VALUES, name="razorpaystatus").create(
        op.get_bind(), checkfirst=True
    )

    op.add_column("Institute", sa.Column("razorpay_key_id", sa.String(), nullable=True))
    op.add_column(
        "Institute", sa.Column("razorpay_key_secret_encrypted", sa.String(), nullable=True)
    )
    op.add_column(
        "Institute",
        sa.Column(
            "razorpay_status",
            postgresql.ENUM(*RAZORPAY_STATUS_VALUES, name="razorpaystatus", create_type=False),
            nullable=False,
            server_default="NOT_CONNECTED",
        ),
    )


def downgrade() -> None:
    op.drop_column("Institute", "razorpay_status")
    op.drop_column("Institute", "razorpay_key_secret_encrypted")
    op.drop_column("Institute", "razorpay_key_id")
    postgresql.ENUM(name="razorpaystatus").drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 3: Verify the migration chain is valid**

```bash
uv run alembic heads
```

Expected: `i3j4k5l6m7n8 (head)`.

- [ ] **Step 4: Apply the migration** — ⚠️ **this connects to the live Supabase Postgres database (shared dev/prod). Confirm with the user before running this command.**

```bash
uv run alembic upgrade head
```

Expected: log line ending in `Running upgrade 00f800b106b9 -> i3j4k5l6m7n8`. All three new columns are nullable-or-defaulted, so this is additive and safe for existing rows.

- [ ] **Step 5: Run the full backend test suite to confirm nothing broke**

```bash
uv run pytest -v
```

Expected: all tests pass (SQLite test DB rebuilds from `Base.metadata.create_all` each run, so it already includes the new columns without needing the migration).

- [ ] **Step 6: Commit**

```bash
git add models/institute_base.py alembic/versions/i3j4k5l6m7n8_institute_razorpay_payout_fields.py
git commit -m "feat(payouts): add razorpay_key_id/secret/status columns to Institute"
```

---

## Task 3: `InstituteService.connect_razorpay()`

**Files:**
- Modify: `services/institute_service.py`
- Modify: `tests/test_institute_service.py`

**Interfaces:**
- Consumes: `services.crypto_service.encrypt_secret` (Task 1), `models.institute_base.RazorpayStatus` (Task 2).
- Produces: `InstituteService.connect_razorpay(db, owner_id: int, key_id: str, key_secret: str) -> InstituteSchema`. Raises `ValueError` if no institute exists for `owner_id`. Task 5 (routes) calls this.

- [ ] **Step 1: Write the failing tests**

In `tests/test_institute_service.py`, add near the top:

```python
from models.institute_base import RazorpayStatus
```

And add these tests at the end of the file:

```python
# --- connect_razorpay ---

async def test_connect_razorpay_encrypts_and_updates(service, mock_db):
    existing = _make_institute(owner_id=4)
    updated = _make_institute(owner_id=4)
    updated.razorpay_key_id = "rzp_live_abc123"
    updated.razorpay_status = RazorpayStatus.CONNECTED
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.connect_razorpay(
            mock_db, owner_id=4, key_id="rzp_live_abc123", key_secret="supersecretvalue"
        )

    assert result is updated
    update_mock.assert_called_once()
    call_args = update_mock.call_args[0]
    assert call_args[1] is existing
    updates = call_args[2]
    assert updates["razorpay_key_id"] == "rzp_live_abc123"
    assert updates["razorpay_status"] == RazorpayStatus.CONNECTED
    # secret must never be stored in plaintext
    assert updates["razorpay_key_secret_encrypted"] != "supersecretvalue"


async def test_connect_razorpay_raises_when_no_institute(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="No institute found"):
            await service.connect_razorpay(
                mock_db, owner_id=999, key_id="rzp_live_x", key_secret="secretvalue"
            )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_institute_service.py -v -k connect_razorpay
```

Expected: FAIL/ERROR — `connect_razorpay` does not exist.

- [ ] **Step 3: Implement `connect_razorpay`**

In `services/institute_service.py`, add the import at the top:

```python
from models.institute_base import InstituteSchema, RazorpayStatus
```

(replacing the existing `from models.institute_base import InstituteSchema` line)

Then add this method to `InstituteService`, right after `update_institute`:

```python
    async def connect_razorpay(
        self, db: AsyncSession, owner_id: int, key_id: str, key_secret: str
    ) -> InstituteSchema:
        """Save an owner's own Razorpay Key ID/Secret; encrypts the secret at rest.

        Raises:
            ValueError: If no institute exists for this owner.
        """
        from services.crypto_service import encrypt_secret

        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            raise ValueError("No institute found for this owner")

        updates = {
            "razorpay_key_id": key_id,
            "razorpay_key_secret_encrypted": encrypt_secret(key_secret),
            "razorpay_status": RazorpayStatus.CONNECTED,
        }
        return await self.institute_repo.update(db, institute, updates)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_institute_service.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add services/institute_service.py tests/test_institute_service.py
git commit -m "feat(payouts): add InstituteService.connect_razorpay()"
```

---

## Task 4: Request/response schemas

**Files:**
- Create: `routes/requests/update_razorpay_credentials_request.py`
- Create: `routes/responses/razorpay_payout_response.py`

**Interfaces:**
- Produces: `UpdateRazorpayCredentialsRequest(razorpay_key_id: str, razorpay_key_secret: str)`; `RazorpayPayoutResponse(status: str, key_id: str | None, secret_configured: bool)`. Task 5 imports both.

- [ ] **Step 1: Create the request schema**

`routes/requests/update_razorpay_credentials_request.py`:

```python
from pydantic import BaseModel, Field


class UpdateRazorpayCredentialsRequest(BaseModel):
    razorpay_key_id: str = Field(min_length=1, max_length=200)
    razorpay_key_secret: str = Field(min_length=1, max_length=500)
```

- [ ] **Step 2: Create the response schema**

`routes/responses/razorpay_payout_response.py`:

```python
from pydantic import BaseModel


class RazorpayPayoutResponse(BaseModel):
    status: str  # "NOT_CONNECTED" | "CONNECTED" | "NEEDS_RECONNECT"
    key_id: str | None = None
    secret_configured: bool
```

No test needed here — these are pure data schemas with no logic, exercised by the route tests in Task 5.

- [ ] **Step 3: Commit**

```bash
git add routes/requests/update_razorpay_credentials_request.py routes/responses/razorpay_payout_response.py
git commit -m "feat(payouts): add request/response schemas for the payouts endpoint"
```

---

## Task 5: `GET`/`PATCH /owner/institute/payouts` routes

**Files:**
- Modify: `routes/owner_route.py`
- Modify: `tests/test_institute_routes.py`

**Interfaces:**
- Consumes: `InstituteService.connect_razorpay` (Task 3), `UpdateRazorpayCredentialsRequest`/`RazorpayPayoutResponse` (Task 4).
- Produces: `GET /owner/institute/payouts` → 200 `RazorpayPayoutResponse` / 404 if owner or institute missing. `PATCH /owner/institute/payouts` → 200 `RazorpayPayoutResponse` / 404 if owner or institute missing / 422 on empty fields. Task 7 (frontend `ownerService.js`) calls these.

- [ ] **Step 1: Write the failing tests**

In `tests/test_institute_routes.py`, update the `_make_institute` helper to include the new fields (replace the existing function):

```python
def _make_institute(owner_id: int = 1, razorpay_status="NOT_CONNECTED", razorpay_key_id=None) -> InstituteSchema:
    from models.institute_base import RazorpayStatus

    inst = MagicMock(spec=InstituteSchema)
    inst.id = 10
    inst.owner_id = owner_id
    inst.name = "Sharma Classes"
    inst.city = "Gurugram"
    inst.created_at = datetime(2026, 5, 1)
    inst.razorpay_status = RazorpayStatus(razorpay_status)
    inst.razorpay_key_id = razorpay_key_id
    inst.razorpay_key_secret_encrypted = "encrypted-blob" if razorpay_key_id else None
    return inst
```

Update the `_setup_institute_service` helper to support `connect_razorpay` (replace the existing function):

```python
def _setup_institute_service(client, existing=None, created=None, updated=None, connected=None, connect_error=None):
    """Wire an InstituteService mock."""
    mock_svc = MagicMock(spec=InstituteService)
    mock_svc.get_institute_by_owner_id = AsyncMock(return_value=existing)
    if created is not None:
        mock_svc.create_institute = AsyncMock(return_value=created)
    if updated is not None:
        mock_svc.update_institute = AsyncMock(return_value=updated)
    if connect_error is not None:
        mock_svc.connect_razorpay = AsyncMock(side_effect=connect_error)
    elif connected is not None:
        mock_svc.connect_razorpay = AsyncMock(return_value=connected)
    from app import app

    app.dependency_overrides[get_institute_service] = lambda: mock_svc
    return mock_svc
```

Then add these tests at the end of the file:

```python
# ─── GET /owner/institute/payouts ─────────────────────────────────────────────


async def test_get_payouts_returns_not_connected_by_default(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    institute = _make_institute(owner_id=owner.id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=institute)

    response = await client.get(
        "/owner/institute/payouts",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_CONNECTED"
    assert body["key_id"] is None
    assert body["secret_configured"] is False


async def test_get_payouts_returns_404_when_no_institute(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=None)

    response = await client.get(
        "/owner/institute/payouts",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404


# ─── PATCH /owner/institute/payouts ────────────────────────────────────────────


async def test_update_payouts_returns_connected_status(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    institute = _make_institute(owner_id=owner.id)
    connected = _make_institute(owner_id=owner.id, razorpay_status="CONNECTED", razorpay_key_id="rzp_live_abc")

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=institute, connected=connected)

    response = await client.patch(
        "/owner/institute/payouts",
        json={"razorpay_key_id": "rzp_live_abc", "razorpay_key_secret": "supersecretvalue"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CONNECTED"
    assert body["key_id"] == "rzp_live_abc"
    assert body["secret_configured"] is True
    assert "razorpay_key_secret" not in body


async def test_update_payouts_rejects_empty_key_id(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=_make_institute(owner_id=owner.id))

    response = await client.patch(
        "/owner/institute/payouts",
        json={"razorpay_key_id": "", "razorpay_key_secret": "supersecretvalue"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 422


async def test_update_payouts_returns_404_when_no_institute(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=None, connect_error=ValueError("No institute found for this owner"))

    response = await client.patch(
        "/owner/institute/payouts",
        json={"razorpay_key_id": "rzp_live_abc", "razorpay_key_secret": "supersecretvalue"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/test_institute_routes.py -v
```

Expected: the 5 new tests FAIL with 404 Not Found (routes don't exist yet).

- [ ] **Step 3: Implement the routes**

In `routes/owner_route.py`, add two imports near the other `routes.requests`/`routes.responses` imports:

```python
from routes.requests.update_razorpay_credentials_request import UpdateRazorpayCredentialsRequest
from routes.responses.razorpay_payout_response import RazorpayPayoutResponse
```

Then add these two route handlers at the end of the file, after `get_institute_qr`:

```python
# ─── GET/PATCH /owner/institute/payouts ───────────────────────────────────────


@router.get(
    "/institute/payouts",
    summary="Get the connection status of the owner's Razorpay payout account",
    response_model=RazorpayPayoutResponse,
)
async def get_razorpay_payouts(
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    institute_service: InstituteServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")
    institute = await institute_service.get_institute_by_owner_id(db=db, owner_id=owner.id)
    if not institute:
        raise HTTPException(status_code=404, detail="No institute found for this owner")

    return RazorpayPayoutResponse(
        status=institute.razorpay_status.value,
        key_id=institute.razorpay_key_id,
        secret_configured=institute.razorpay_key_secret_encrypted is not None,
    )


@router.patch(
    "/institute/payouts",
    summary="Save the owner's own Razorpay Key ID/Secret (encrypted at rest)",
    response_model=RazorpayPayoutResponse,
)
async def update_razorpay_payouts(
    request: UpdateRazorpayCredentialsRequest,
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    institute_service: InstituteServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")

    try:
        institute = await institute_service.connect_razorpay(
            db=db,
            owner_id=owner.id,
            key_id=request.razorpay_key_id,
            key_secret=request.razorpay_key_secret,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return RazorpayPayoutResponse(
        status=institute.razorpay_status.value,
        key_id=institute.razorpay_key_id,
        secret_configured=institute.razorpay_key_secret_encrypted is not None,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/test_institute_routes.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run the full backend suite**

```bash
uv run pytest -v
```

Expected: all tests pass (note the count — should be +9 from this plan's Tasks 1, 3, 5 combined vs. baseline).

- [ ] **Step 6: Commit**

```bash
git add routes/owner_route.py tests/test_institute_routes.py
git commit -m "feat(payouts): add GET/PATCH /owner/institute/payouts routes"
```

---

## Task 6: Create the frontend branch

**Files:**
- No file changes — environment setup only

- [ ] **Step 1: Create the branch inside batchbookui**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook/batchbookui
git checkout master
git pull origin master
git checkout -b feat/byo-razorpay-settings-ui
```

Expected: `Switched to a new branch 'feat/byo-razorpay-settings-ui'`, branched from the latest `master` (which already includes the merged A.3 bug fixes).

- [ ] **Step 2: Verify baseline tests pass**

```bash
npm test
```

Expected: all existing tests pass (green). Note the count.

---

## Task 7: `ownerService.js` payout functions

**Files:**
- Modify: `batchbookui/src/services/ownerService.js`

**Interfaces:**
- Consumes: backend `GET`/`PATCH /owner/institute/payouts` (Task 5).
- Produces: `getRazorpayPayoutStatus(): Promise<{status, key_id, secret_configured}>`, `saveRazorpayCredentials(keyId, keySecret): Promise<{status, key_id, secret_configured}>`. Tasks 8 and 9 import both.

- [ ] **Step 1: Add the functions**

In `batchbookui/src/services/ownerService.js`, add this block at the end of the file, after the `getOwnerStats` section:

```js
// ─── Razorpay Payouts (/owner/institute/payouts) ──────────────────────────────

/** @returns {Promise<{status: 'NOT_CONNECTED'|'CONNECTED'|'NEEDS_RECONNECT', key_id: string|null, secret_configured: boolean}>} */
export async function getRazorpayPayoutStatus() {
  const { data } = await api.get('/owner/institute/payouts');
  return data;
}

/**
 * @param {string} keyId
 * @param {string} keySecret
 * @returns {Promise<{status: string, key_id: string|null, secret_configured: boolean}>}
 */
export async function saveRazorpayCredentials(keyId, keySecret) {
  const { data } = await api.patch('/owner/institute/payouts', {
    razorpay_key_id: keyId,
    razorpay_key_secret: keySecret,
  });
  return data;
}
```

No dedicated test for this file — it's a thin axios wrapper, exercised by the component tests in Tasks 8 and 9 (same pattern the rest of `ownerService.js` already follows).

- [ ] **Step 2: Commit**

```bash
git add src/services/ownerService.js
git commit -m "feat: add getRazorpayPayoutStatus/saveRazorpayCredentials to ownerService"
```

---

## Task 8: `SettingsPage.jsx` — Payouts UI

**Files:**
- Create: `batchbookui/src/pages/owner/SettingsPage.jsx`
- Create: `batchbookui/src/test/SettingsPage.test.jsx`
- Modify: `batchbookui/src/pages/owner/OwnerDashboard.jsx`

**Interfaces:**
- Consumes: `getRazorpayPayoutStatus`, `saveRazorpayCredentials` (Task 7).
- Produces: default export `SettingsPage` (no props). `OwnerDashboard`'s `NAV_ITEMS` gains a `settings` entry; `MainContent` renders `<SettingsPage />` when `section === 'settings'`.

- [ ] **Step 1: Write the failing test**

Create `batchbookui/src/test/SettingsPage.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SettingsPage from '../pages/owner/SettingsPage';

vi.mock('../services/ownerService', () => ({
  getRazorpayPayoutStatus: vi.fn(),
  saveRazorpayCredentials: vi.fn(),
}));

import { getRazorpayPayoutStatus, saveRazorpayCredentials } from '../services/ownerService';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SettingsPage — Payouts', () => {
  it('shows Not Connected status by default', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'NOT_CONNECTED', key_id: null, secret_configured: false,
    });

    render(<SettingsPage />);

    await waitFor(() => expect(getRazorpayPayoutStatus).toHaveBeenCalledOnce());
    expect(await screen.findByText(/not connected/i)).toBeInTheDocument();
  });

  it('shows Connected status and existing key id when already configured', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'CONNECTED', key_id: 'rzp_live_abc123', secret_configured: true,
    });

    render(<SettingsPage />);

    expect(await screen.findByText(/^connected$/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('rzp_live_abc123')).toBeInTheDocument();
  });

  it('saving valid credentials calls saveRazorpayCredentials and updates status', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'NOT_CONNECTED', key_id: null, secret_configured: false,
    });
    saveRazorpayCredentials.mockResolvedValue({
      status: 'CONNECTED', key_id: 'rzp_live_new', secret_configured: true,
    });

    render(<SettingsPage />);
    await waitFor(() => screen.getByLabelText(/key id/i));

    fireEvent.change(screen.getByLabelText(/key id/i), { target: { value: 'rzp_live_new' } });
    fireEvent.change(screen.getByLabelText(/key secret/i), { target: { value: 'topsecretvalue' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(saveRazorpayCredentials).toHaveBeenCalledWith('rzp_live_new', 'topsecretvalue')
    );
    expect(await screen.findByText(/^connected$/i)).toBeInTheDocument();
  });

  it('shows an error message when saving fails', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'NOT_CONNECTED', key_id: null, secret_configured: false,
    });
    saveRazorpayCredentials.mockRejectedValue({
      response: { data: { detail: 'No institute found for this owner' } },
    });

    render(<SettingsPage />);
    await waitFor(() => screen.getByLabelText(/key id/i));

    fireEvent.change(screen.getByLabelText(/key id/i), { target: { value: 'rzp_live_new' } });
    fireEvent.change(screen.getByLabelText(/key secret/i), { target: { value: 'topsecretvalue' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    expect(await screen.findByText(/no institute found for this owner/i)).toBeInTheDocument();
  });
});

describe('SettingsPage — OwnerDashboard integration', () => {
  it('Settings nav item is rendered in OwnerDashboard', async () => {
    const { default: OwnerDashboard } = await import('../pages/owner/OwnerDashboard');
    const { AuthProvider } = await import('../context/AuthContext');
    const { MemoryRouter } = await import('react-router-dom');

    render(
      <MemoryRouter>
        <AuthProvider>
          <OwnerDashboard />
        </AuthProvider>
      </MemoryRouter>
    );

    await waitFor(() => expect(screen.getByText('Settings')).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
npm test -- --reporter=verbose 2>&1 | grep -A 5 "SettingsPage"
```

Expected: FAIL — `SettingsPage` module not found.

- [ ] **Step 3: Create `SettingsPage.jsx`**

Create `batchbookui/src/pages/owner/SettingsPage.jsx`:

```jsx
import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Skeleton,
  TextField,
  Typography,
} from '@mui/material';
import LockIcon from '@mui/icons-material/Lock';
import { getRazorpayPayoutStatus, saveRazorpayCredentials } from '../../services/ownerService';

// ─── Design tokens (matches existing owner pages) ─────────────────────────────
const T = {
  bg: '#121212',
  surface: '#1E1E1E',
  surfVar: '#2C2C2C',
  primary: '#BB86FC',
  fg1: '#FFFFFF',
  fg2: '#B0B0B0',
  fg3: 'rgba(255,255,255,0.35)',
  outline: 'rgba(255,255,255,0.10)',
  sans: "'DM Sans', system-ui, sans-serif",
  error: '#CF6679',
  connected: '#43A047',
  pending: '#FB8C00',
};

function statusChipProps(status) {
  if (status === 'CONNECTED') {
    return { label: 'Connected', sx: { bgcolor: 'rgba(67,160,71,0.15)', color: T.connected } };
  }
  if (status === 'NEEDS_RECONNECT') {
    return { label: 'Needs Reconnect', sx: { bgcolor: 'rgba(251,140,0,0.15)', color: T.pending } };
  }
  return { label: 'Not Connected', sx: { bgcolor: T.surfVar, color: T.fg2 } };
}

/**
 * SettingsPage — owner "Payouts" settings.
 *
 * Lets the owner paste their own Razorpay Key ID/Secret so fee payments
 * settle directly into their own account (BYO-Razorpay, Phase F).
 */
export default function SettingsPage() {
  const [status, setStatus] = useState('NOT_CONNECTED');
  const [keyId, setKeyId] = useState('');
  const [keySecret, setKeySecret] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    getRazorpayPayoutStatus()
      .then((data) => {
        setStatus(data.status);
        setKeyId(data.key_id ?? '');
      })
      .catch(() => setError('Failed to load payout settings.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setError('');
    setSuccess(false);
    setSaving(true);
    try {
      const data = await saveRazorpayCredentials(keyId, keySecret);
      setStatus(data.status);
      setKeyId(data.key_id ?? '');
      setKeySecret('');
      setSuccess(true);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to save Razorpay credentials.');
    } finally {
      setSaving(false);
    }
  }

  const chip = statusChipProps(status);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, fontFamily: T.sans, maxWidth: 560 }}>
      <Typography sx={{ fontFamily: T.sans, fontSize: 22, fontWeight: 700, color: T.fg1, mb: 3 }}>
        Settings
      </Typography>

      <Card
        elevation={0}
        sx={{ bgcolor: T.surface, border: `1px solid ${T.outline}`, borderRadius: '16px' }}
      >
        <CardContent sx={{ p: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
            <LockIcon sx={{ color: T.primary, fontSize: 22 }} />
            <Typography sx={{ fontFamily: T.sans, fontSize: 16, fontWeight: 700, color: T.fg1 }}>
              Payouts
            </Typography>
            {loading ? (
              <Skeleton variant="rounded" width={90} height={24} sx={{ bgcolor: T.surfVar }} />
            ) : (
              <Chip size="small" label={chip.label} sx={{ ...chip.sx, fontFamily: T.sans, fontSize: 12 }} />
            )}
          </Box>

          <Typography sx={{ fontFamily: T.sans, fontSize: 13, color: T.fg2, mb: 2.5 }}>
            You'll need your own Razorpay account to collect fees online — sign up at{' '}
            <strong>razorpay.com</strong>, complete your own KYC, then paste your Key ID and
            Key Secret below. Payments will settle directly into your Razorpay account;
            BatchBook never holds or moves your money.
          </Typography>

          {error && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: '12px' }}>
              {error}
            </Alert>
          )}
          {success && (
            <Alert severity="success" sx={{ mb: 2, borderRadius: '12px' }}>
              Razorpay credentials saved.
            </Alert>
          )}

          {loading ? (
            <Skeleton variant="rounded" height={96} sx={{ bgcolor: T.surfVar, borderRadius: '12px' }} />
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                label="Key ID"
                value={keyId}
                onChange={(e) => setKeyId(e.target.value)}
                placeholder="rzp_live_..."
                size="small"
                fullWidth
              />
              <TextField
                label="Key Secret"
                type="password"
                value={keySecret}
                onChange={(e) => setKeySecret(e.target.value)}
                placeholder={status === 'CONNECTED' ? 'Enter secret again to update' : ''}
                helperText={
                  status === 'CONNECTED'
                    ? "For security we never show your saved secret — re-enter it to change your credentials."
                    : ''
                }
                size="small"
                fullWidth
              />
              <Button
                variant="contained"
                onClick={handleSave}
                disabled={saving || !keyId || !keySecret}
                sx={{
                  alignSelf: 'flex-start',
                  fontFamily: T.sans,
                  textTransform: 'none',
                  borderRadius: '10px',
                  bgcolor: T.primary,
                  color: '#000',
                  fontWeight: 600,
                  '&:hover': { bgcolor: '#9c5fdc' },
                }}
              >
                {saving ? 'Saving…' : 'Save'}
              </Button>
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
```

- [ ] **Step 4: Wire `settings` into `OwnerDashboard.jsx`**

In `batchbookui/src/pages/owner/OwnerDashboard.jsx`:

Add the import near the other page imports (after `import StudentsPage from './StudentsPage';`):

```jsx
import SettingsPage from './SettingsPage';
```

Add a `SettingsIcon` import near the other `@mui/icons-material` imports:

```jsx
import SettingsIcon from '@mui/icons-material/Settings';
```

Add a `settings` entry to `NAV_ITEMS`, after the `tests` entry:

```jsx
  {
    id: 'tests',
    label: 'Tests',
    icon: <SchoolIcon />,
    description: 'Track student test scores',
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: <SettingsIcon />,
    description: 'Payouts and account settings',
  },
];
```

Add a `settings` case in `MainContent`, and pass `onNavigateToSettings` to `FeesPage` (replace the existing `if (section === 'fees')` block and the `if (section === 'tests')` block):

```jsx
  if (section === 'fees') {
    return <FeesPage onNavigateToSettings={() => onSectionChange('settings')} />;
  }

  if (section === 'attendance') {
    return <AttendancePage />;
  }

  if (section === 'tests') {
    return <TestsPage />;
  }

  if (section === 'settings') {
    return <SettingsPage />;
  }
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
npm test
```

Expected: all tests pass, including all 5 new `SettingsPage` tests.

- [ ] **Step 6: Commit**

```bash
git add src/pages/owner/SettingsPage.jsx src/pages/owner/OwnerDashboard.jsx src/test/SettingsPage.test.jsx
git commit -m "feat: add Settings > Payouts page for BYO-Razorpay credentials"
```

---

## Task 9: "Connect Payouts" banner on `FeesPage.jsx`

**Files:**
- Modify: `batchbookui/src/pages/owner/FeesPage.jsx`
- Modify: `batchbookui/src/test/FeesPage.test.jsx`

**Interfaces:**
- Consumes: `getRazorpayPayoutStatus` (Task 7), `onNavigateToSettings` prop (wired in Task 8, Step 4).

- [ ] **Step 1: Write the failing tests**

In `batchbookui/src/test/FeesPage.test.jsx`, find the `vi.mock('../services/ownerService', ...)` block near the top and add `getRazorpayPayoutStatus` to the mocked exports (add this line inside the mock object, alongside the other mocked functions):

```js
  getRazorpayPayoutStatus: vi.fn(),
```

Then find the `beforeEach` block and add a default mock resolution so existing tests aren't affected:

```js
  getRazorpayPayoutStatus.mockResolvedValue({ status: 'CONNECTED', key_id: 'rzp_live_x', secret_configured: true });
```

(Add the corresponding import: extend the existing `import { ... } from '../services/ownerService';` line at the top of the test file to include `getRazorpayPayoutStatus`.)

Then add these tests at the end of the file, inside a new `describe` block:

```jsx
describe('FeesPage — Connect Payouts banner', () => {
  it('shows the banner when payouts are not connected', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({ status: 'NOT_CONNECTED', key_id: null, secret_configured: false });

    render(<FeesPage />);

    expect(await screen.findByText(/connect your razorpay account/i)).toBeInTheDocument();
  });

  it('does not show the banner when payouts are connected', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({ status: 'CONNECTED', key_id: 'rzp_live_x', secret_configured: true });

    render(<FeesPage />);

    await waitFor(() => expect(getRazorpayPayoutStatus).toHaveBeenCalledOnce());
    expect(screen.queryByText(/connect your razorpay account/i)).not.toBeInTheDocument();
  });

  it('calls onNavigateToSettings when the banner action is clicked', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({ status: 'NOT_CONNECTED', key_id: null, secret_configured: false });
    const onNavigateToSettings = vi.fn();

    render(<FeesPage onNavigateToSettings={onNavigateToSettings} />);

    const banner = await screen.findByText(/connect your razorpay account/i);
    fireEvent.click(screen.getByRole('button', { name: /connect payouts/i }));

    expect(onNavigateToSettings).toHaveBeenCalledOnce();
    expect(banner).toBeInTheDocument(); // sanity: banner was actually rendered before the click
  });

  it('dismissing the banner hides it', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({ status: 'NOT_CONNECTED', key_id: null, secret_configured: false });

    render(<FeesPage />);

    await screen.findByText(/connect your razorpay account/i);
    fireEvent.click(screen.getByRole('button', { name: /close/i }));

    expect(screen.queryByText(/connect your razorpay account/i)).not.toBeInTheDocument();
  });
});
```

Check the exact import list at the top of `batchbookui/src/test/FeesPage.test.jsx` first (`render, screen, fireEvent, waitFor` etc. from `@testing-library/react`) and add any of `fireEvent`/`waitFor` that aren't already imported.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
npm test -- --reporter=verbose 2>&1 | grep -A 5 "Connect Payouts banner"
```

Expected: FAIL — banner text not found.

- [ ] **Step 3: Implement the banner**

In `batchbookui/src/pages/owner/FeesPage.jsx`:

Add the import, alongside the other `ownerService` imports:

```jsx
import {
  getBatches,
  getFeeDashboard,
  getBatchFees,
  getFeeStructure,
  generateMonthlyRecords,
  sendFeeReminder,
  getRazorpayPayoutStatus,
} from '../../services/ownerService';
```

In the `FeesPage` component (the default export, starting around line 526), add two new pieces of state right after `const [batchError, setBatchError] = useState('');`:

```jsx
  const [payoutsConnected, setPayoutsConnected] = useState(true); // assume connected until checked, to avoid a flash
  const [bannerDismissed, setBannerDismissed] = useState(false);
```

Add a `useEffect` to check payout status on mount, right after the existing `loadDashboard`/`loadBatches` `useEffect`s:

```jsx
  useEffect(() => {
    getRazorpayPayoutStatus()
      .then((data) => setPayoutsConnected(data.status === 'CONNECTED'))
      .catch(() => {}); // fail silent — banner just won't show
  }, []);
```

Add the `onNavigateToSettings` prop to the component signature (replace `export default function FeesPage() {`):

```jsx
export default function FeesPage({ onNavigateToSettings } = {}) {
```

Add the banner JSX right after the `{/* ── Header ─────────────────────────────────── */}` block closes (i.e., immediately before the `{/* ── Summary cards ──────────────────────────── */}` comment):

```jsx
      {!payoutsConnected && !bannerDismissed && (
        <Alert
          severity="warning"
          onClose={() => setBannerDismissed(true)}
          action={
            <Button
              size="small"
              onClick={() => onNavigateToSettings?.()}
              sx={{ fontFamily: T.sans, textTransform: 'none', fontWeight: 700 }}
            >
              Connect Payouts
            </Button>
          }
          sx={{ mb: 3, borderRadius: '12px' }}
        >
          Connect your Razorpay account to start collecting fees online.
        </Alert>
      )}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
npm test
```

Expected: all tests pass, including the 4 new banner tests and all pre-existing `FeesPage` tests (unaffected, since `payoutsConnected` defaults to `true`).

- [ ] **Step 5: Commit**

```bash
git add src/pages/owner/FeesPage.jsx src/test/FeesPage.test.jsx
git commit -m "feat: show Connect Payouts banner on Fees page when Razorpay isn't connected"
```

---

## Task 10: Push, PR, and bump the submodule pointer

**Files:**
- No code changes — git operations only

> **Confirm with the user before Steps 1, 2, 4, and 5** — pushing branches and opening PRs are visible/shared-state actions.

- [ ] **Step 1: Push the frontend branch and open its PR**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook/batchbookui
git push -u origin feat/byo-razorpay-settings-ui
gh pr create \
  --title "feat: BYO-Razorpay Settings page (Phase F, Task F.1)" \
  --body "$(cat <<'EOF'
## Summary

- New Settings > Payouts page: owner pastes their own Razorpay Key ID/Secret.
- Fees page shows a dismissible "Connect Payouts" banner when not connected.
- Depends on the backend PR adding `GET`/`PATCH /owner/institute/payouts`.

Part of Phase F (BYO-Razorpay multi-tenant payments) — schema + UI only.
Follow-ups (separate PRs): F.2 credential validation, F.3 per-institute
Razorpay client in fee_service, F.4 per-institute webhooks.

## Test plan

- [ ] `npm test` — all tests pass
- [ ] Manual: Settings > Payouts renders, paste test values, Save shows "Connected"
- [ ] Manual: Fees page shows the banner for an institute with no keys connected

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed. Copy it.

- [ ] **Step 2: Push the backend branch and open its PR**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
git push -u origin feat/byo-razorpay-payouts
gh pr create \
  --title "feat: Institute Razorpay payout fields + Settings routes (Phase F, Task F.1)" \
  --body "$(cat <<'EOF'
## Summary

- `Institute` gains `razorpay_key_id`, `razorpay_key_secret_encrypted` (Fernet,
  encrypted at rest), `razorpay_status` (NOT_CONNECTED/CONNECTED/NEEDS_RECONNECT).
- New `GET`/`PATCH /owner/institute/payouts` — owner reads/saves their own
  Razorpay credentials. Secret is never returned, only `secret_configured: bool`.
- Requires `RAZORPAY_ENCRYPTION_KEY` in `.env` — generate with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  and set it on Render too before this deploys.

Part of Phase F (BYO-Razorpay multi-tenant payments) — schema + endpoints only.
Follow-ups (separate PRs): F.2 credential validation, F.3 per-institute
Razorpay client in fee_service, F.4 per-institute webhooks.

## Test plan

- [ ] `uv run pytest -v` — all tests pass
- [ ] `RAZORPAY_ENCRYPTION_KEY` set in Render dashboard before merge

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed. Copy it.

- [ ] **Step 3: Note the submodule bump is deferred**

Do **not** bump the `batchbookui` submodule pointer in the parent repo yet — that should happen only after the `batchbookui` PR is reviewed and merged to its `master` (the parent repo's submodule pointer must reference a commit on `batchbookui`'s `master`, not a feature branch). Track this as a follow-up once both PRs are approved.

- [ ] **Step 4 (after both PRs are merged, in a later session): Bump the submodule pointer**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook/batchbookui
git checkout master && git pull origin master
cd /Users/bedantsharma/PycharmProjects/BatchBook
git add batchbookui
git commit -m "chore: bump batchbookui submodule — BYO-Razorpay Settings page"
git push origin master
```
