# Payment Link Callback + Institute-Scoped Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give parents a BatchBook landing page after paying a Razorpay link, make payment links use each institute's own connected Razorpay account, and add a recurring (+ manually triggerable) job that backfills missing payment links for last month's fee records.

**Architecture:** Backend changes live in `BatchBook/` (FastAPI + SQLAlchemy). One frontend change lives in the `batchbookui/` git submodule (a separate repo). An in-process APScheduler job runs inside the FastAPI app, guarded by a Postgres advisory lock so it can't double-run across the two prod uvicorn workers; the same underlying service method is reachable via a manual, admin-secret-protected HTTP endpoint.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, `razorpay` SDK, APScheduler (new dependency), React 19 + MUI 9 (frontend, submodule).

**Full spec:** `docs/superpowers/specs/2026-07-02-payment-link-callback-and-backfill-design.md` — read it first for the decisions and rationale behind each task below.

## Global Constraints

- Package manager: `uv` — use `uv add <pkg>` / `uv run <cmd>`, never bare `pip`/`python`.
- Linter/formatter: `ruff`, line length 100. Auto-fix is on.
- Test runner: `pytest`, async mode `auto`. Run with `uv run pytest`.
- Frontend tests: `vitest`, run from inside `batchbookui/` with `npx vitest run <path>`.
- `batchbookui/` is a **separate git repo** mounted as a submodule. Its commits use its own git identity and are pushed directly to `origin/master` in that repo (this project's small enough that submodule changes don't get their own PR — see submodule rules in the root `CLAUDE.md`). Do **not** run `git add batchbookui/` (trailing slash) from the parent repo.
- All backend tasks commit to one feature branch in the `BatchBook` repo (create it before Task 1: `git checkout -b feat/payment-link-callback-and-backfill`).
- Every task's commit message follows this repo's existing convention: `type(scope): summary` (see `git log --oneline` for examples like `fix(payouts): ...`, `feat(fees): ...`).

---

### Task 1: Payment-link callback URL + `FRONTEND_BASE_URL` config

**Files:**
- Modify: `config.py`
- Modify: `services/fee_service.py`
- Modify: `routes/fee_route.py`
- Test: `tests/test_fee_service.py`

**Interfaces:**
- Produces: `Settings.frontend_base_url: str` (default `"https://batchbook.in"`), consumed by Tasks 6/7 for `admin_backfill_secret`/`enable_scheduler` siblings on the same `Settings` class, and by Task 6's admin route indirectly (no direct dependency, just the same file).

- [ ] **Step 1: Write the failing test**

Open `tests/test_fee_service.py`. Change the import line near the top from:

```python
from unittest.mock import AsyncMock, MagicMock
```

to:

```python
from unittest.mock import AsyncMock, MagicMock, patch
```

Then add this test in the `generate_payment_link` section (after `test_generate_payment_link_standard_when_payment_method_none`, before `test_generate_payment_link_raises_when_record_not_found`):

```python
async def test_generate_payment_link_includes_callback_url():
    """callback_url/callback_method route the payer back to the success page."""
    svc = FeeService()
    db = MagicMock()
    razorpay_client = MagicMock()

    record = _make_fee_record(
        record_id=6,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
        month=date(2026, 5, 1),
    )

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_record_by_id = AsyncMock(return_value=record)
    svc.fee_repo.update_payment_link = AsyncMock(return_value=record)
    svc._create_razorpay_link = AsyncMock(return_value={"short_url": "https://rzp.io/i/cb"})

    with patch("services.fee_service.get_settings") as mock_settings:
        mock_settings.return_value.frontend_base_url = "https://batchbook.in"
        await svc.generate_payment_link(db=db, record_id=6, razorpay_client=razorpay_client)

    _, data_sent = svc._create_razorpay_link.call_args.args
    assert data_sent["callback_url"] == "https://batchbook.in/payment-success"
    assert data_sent["callback_method"] == "get"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fee_service.py::test_generate_payment_link_includes_callback_url -v`
Expected: FAIL — `KeyError: 'callback_url'` (the key doesn't exist in `data_sent` yet).

- [ ] **Step 3: Add `frontend_base_url` to Settings**

In `config.py`, add a field to the `Settings` class, right after `razorpay_encryption_key`:

```python
    razorpay_encryption_key: str | None = None
    frontend_base_url: str = "https://batchbook.in"
```

- [ ] **Step 4: Wire callback_url into generate_payment_link**

In `services/fee_service.py`, add the import to the existing first-party import group (`config` sorts alphabetically before `models`):

Find:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.fee_record_base import FeeRecordSchema, FeeStatus
```

Replace with:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.fee_record_base import FeeRecordSchema, FeeStatus
```

Then in `generate_payment_link`, find:

```python
        data = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "reminder_enable": True,
        }
        if payment_method == PaymentMethod.UPI:
            data["upi_link"] = "true"
```

Replace with:

```python
        settings = get_settings()
        data = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "reminder_enable": True,
            "callback_url": f"{settings.frontend_base_url}/payment-success",
            "callback_method": "get",
        }
        if payment_method == PaymentMethod.UPI:
            data["upi_link"] = "true"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_fee_service.py -v`
Expected: All tests in this file PASS (the new test plus all pre-existing ones — the `data` dict got two new keys but no existing test asserts the full dict shape, only specific keys, so nothing else breaks).

- [ ] **Step 6: Replace hardcoded join-link URLs with the new setting**

In `routes/fee_route.py`, add the import (alphabetically, after the `clients.supabase_client` import):

```python
from clients.razorpay_client import get_razorpay_client
from clients.supabase_client import get_supabase_client
from config import get_settings
```

Then find (in `send_fee_reminder_for_record`):

```python
    inst = await institute_service.institute_repo.get_by_id(db, institute_id)
    join_url = f"https://batchbook.in/join/{inst.join_code}" if inst and inst.join_code else None
    link_text = fee_record.payment_link or "Contact your institute"
    amount_str = (
        f"{int(amount_pending):,}"
        if amount_pending == int(amount_pending)
        else f"{float(amount_pending):.2f}"
    )
    components = _body(student.name or "Student", amount_str, batch.name, due_date, link_text)
```

Replace with:

```python
    inst = await institute_service.institute_repo.get_by_id(db, institute_id)
    join_url = (
        f"{get_settings().frontend_base_url}/join/{inst.join_code}"
        if inst and inst.join_code
        else None
    )
    link_text = fee_record.payment_link or "Contact your institute"
    amount_str = (
        f"{int(amount_pending):,}"
        if amount_pending == int(amount_pending)
        else f"{float(amount_pending):.2f}"
    )
    components = _body(student.name or "Student", amount_str, batch.name, due_date, link_text)
```

And find the identical hardcoded line in `send_fee_reminders_for_all`:

```python
    inst = await institute_service.institute_repo.get_by_id(db, institute_id)
    join_url = f"https://batchbook.in/join/{inst.join_code}" if inst and inst.join_code else None
```

Replace with:

```python
    inst = await institute_service.institute_repo.get_by_id(db, institute_id)
    join_url = (
        f"{get_settings().frontend_base_url}/join/{inst.join_code}"
        if inst and inst.join_code
        else None
    )
```

- [ ] **Step 7: Run the full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: All tests PASS (no test in this repo asserts the literal hardcoded `batchbook.in` string from these two call sites — `frontend_base_url` defaults to the same value, so behavior is unchanged unless the env var is set).

- [ ] **Step 8: Commit**

```bash
git add config.py services/fee_service.py routes/fee_route.py tests/test_fee_service.py
git commit -m "feat(fees): add callback_url to payment links and FRONTEND_BASE_URL setting"
```

---

### Task 2: Frontend payment success page

**Files:**
- Create: `batchbookui/src/components/PaymentSuccess.jsx`
- Modify: `batchbookui/src/App.jsx`
- Create: `batchbookui/src/test/PaymentSuccess.test.jsx`

**Interfaces:**
- Produces: route `/payment-success` in the frontend app — this is the exact path Task 1's `callback_url` points at (`{frontend_base_url}/payment-success`). No other task depends on this one; it can be done in parallel with any backend task.

- [ ] **Step 1: Write the failing test**

Create `batchbookui/src/test/PaymentSuccess.test.jsx`:

```jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PaymentSuccess from '../components/PaymentSuccess';

describe('PaymentSuccess', () => {
  it('shows a payment received confirmation', () => {
    render(
      <MemoryRouter>
        <PaymentSuccess />
      </MemoryRouter>
    );
    expect(screen.getByText('Payment received')).toBeInTheDocument();
    expect(screen.getByText(/institute will confirm/i)).toBeInTheDocument();
  });

  it('renders a success icon with an accessible label', () => {
    render(
      <MemoryRouter>
        <PaymentSuccess />
      </MemoryRouter>
    );
    expect(screen.getByRole('img', { name: /payment successful/i })).toBeInTheDocument();
  });

  it('renders a Done button', () => {
    render(
      <MemoryRouter>
        <PaymentSuccess />
      </MemoryRouter>
    );
    expect(screen.getByRole('button', { name: /done/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `batchbookui/`): `npx vitest run src/test/PaymentSuccess.test.jsx`
Expected: FAIL — cannot resolve `../components/PaymentSuccess` (file doesn't exist yet).

- [ ] **Step 3: Create the PaymentSuccess component**

Create `batchbookui/src/components/PaymentSuccess.jsx`:

```jsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Card, Typography, Button } from '@mui/material';
import { keyframes } from '@emotion/react';

const drawCircle = keyframes`
  to { stroke-dashoffset: 0; }
`;

const drawCheck = keyframes`
  to { stroke-dashoffset: 0; }
`;

export default function PaymentSuccess() {
  const navigate = useNavigate();

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Card
        sx={{
          width: '100%',
          maxWidth: 400,
          p: 5,
          textAlign: 'center',
          borderRadius: 4,
          boxShadow: 3,
          bgcolor: 'background.paper',
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
          <svg width="88" height="88" viewBox="0 0 88 88" fill="none" role="img" aria-label="Payment successful">
            <circle
              cx="44"
              cy="44"
              r="40"
              stroke="#03DAC6"
              strokeWidth="4"
              fill="none"
              strokeDasharray="251"
              strokeDashoffset="251"
              style={{ animation: `${drawCircle} 0.6s ease-out forwards` }}
            />
            <path
              d="M26 45 L39 58 L62 32"
              stroke="#03DAC6"
              strokeWidth="4"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="50"
              strokeDashoffset="50"
              style={{ animation: `${drawCheck} 0.4s ease-out 0.5s forwards` }}
            />
          </svg>
        </Box>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
          Payment received
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
          Your institute will confirm it shortly.
        </Typography>
        <Button
          variant="contained"
          color="primary"
          fullWidth
          size="large"
          onClick={() => navigate('/')}
          sx={{ py: 1.5, borderRadius: 2, fontWeight: 700 }}
        >
          Done
        </Button>
      </Card>
    </Box>
  );
}
```

- [ ] **Step 4: Register the route**

In `batchbookui/src/App.jsx`, add the import after `import PhoneLogin from './components/PhoneLogin';`:

```jsx
import PhoneLogin from './components/PhoneLogin';
import PaymentSuccess from './components/PaymentSuccess';
```

And add the route inside the `{/* ── Public routes ─────────────────────────────────── */}` block, after the `/join/:joinCode` route:

```jsx
            <Route path="/join/:joinCode" element={<JoinInstitute />} />
            <Route path="/payment-success" element={<PaymentSuccess />} />
```

- [ ] **Step 5: Run test to verify it passes**

Run (from `batchbookui/`): `npx vitest run src/test/PaymentSuccess.test.jsx`
Expected: All 3 tests PASS.

- [ ] **Step 6: Run the full frontend test suite to check for regressions**

Run (from `batchbookui/`): `npx vitest run`
Expected: All tests PASS.

- [ ] **Step 7: Commit and push (submodule — its own repo, its own history)**

```bash
cd batchbookui
git add src/components/PaymentSuccess.jsx src/App.jsx src/test/PaymentSuccess.test.jsx
git commit -m "feat: add animated payment success page at /payment-success"
git push origin master
cd ..
```

---

### Task 3: Per-institute Razorpay client builder

**Files:**
- Modify: `clients/razorpay_client.py`
- Modify: `tests/test_razorpay_client.py`

**Interfaces:**
- Produces: `build_institute_razorpay_client(institute: InstituteSchema) -> razorpay.Client | None` — consumed by Task 4 (single-record payment-link route) and Task 5 (`FeeService.backfill_missing_payment_links`).

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_razorpay_client.py`:

```python
"""Unit tests for clients/razorpay_client.py."""

from unittest.mock import patch

import pytest

import clients.razorpay_client as rp_module
from models.institute_base import InstituteSchema, RazorpayStatus
```

(only the last import line is new — `pytest`, `patch`, `rp_module` already exist at the top of the file).

Then append these tests at the end of the file:

```python
def _make_institute(status=RazorpayStatus.CONNECTED, key_id="rzp_live_abc", secret_encrypted="enc-blob"):
    from unittest.mock import MagicMock

    inst = MagicMock(spec=InstituteSchema)
    inst.razorpay_status = status
    inst.razorpay_key_id = key_id
    inst.razorpay_key_secret_encrypted = secret_encrypted
    return inst


def test_build_institute_razorpay_client_returns_none_when_not_connected():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(status=RazorpayStatus.NOT_CONNECTED)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_returns_none_when_needs_reconnect():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(status=RazorpayStatus.NEEDS_RECONNECT)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_returns_none_when_missing_key_id():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(key_id=None)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_returns_none_when_missing_secret():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute(secret_encrypted=None)
    assert build_institute_razorpay_client(institute) is None


def test_build_institute_razorpay_client_builds_client_when_connected():
    from clients.razorpay_client import build_institute_razorpay_client

    institute = _make_institute()
    with patch("clients.razorpay_client.decrypt_secret", return_value="plain-secret") as mock_decrypt:
        with patch("clients.razorpay_client.razorpay.Client") as mock_cls:
            build_institute_razorpay_client(institute)

            mock_decrypt.assert_called_once_with("enc-blob")
            mock_cls.assert_called_once_with(auth=("rzp_live_abc", "plain-secret"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_razorpay_client.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_institute_razorpay_client'`.

- [ ] **Step 3: Implement build_institute_razorpay_client**

In `clients/razorpay_client.py`, replace the full file contents with:

```python
import razorpay

from config import get_settings
from models.institute_base import InstituteSchema, RazorpayStatus
from services.crypto_service import decrypt_secret

_client: razorpay.Client | None = None


def get_razorpay_client() -> razorpay.Client:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise RuntimeError(
                "Razorpay credentials not configured — "
                "set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env"
            )
        _client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))
    return _client


def build_institute_razorpay_client(institute: InstituteSchema) -> razorpay.Client | None:
    """Build a Razorpay client using an institute's own connected credentials.

    Returns None if the institute hasn't connected Razorpay (status != CONNECTED)
    or is missing either credential field, so callers can treat "not connected"
    as a normal, expected case rather than an exception.
    """
    if institute.razorpay_status != RazorpayStatus.CONNECTED:
        return None
    if not institute.razorpay_key_id or not institute.razorpay_key_secret_encrypted:
        return None
    secret = decrypt_secret(institute.razorpay_key_secret_encrypted)
    return razorpay.Client(auth=(institute.razorpay_key_id, secret))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_razorpay_client.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/razorpay_client.py tests/test_razorpay_client.py
git commit -m "feat(razorpay): build a client from an institute's own connected credentials"
```

---

### Task 4: Wire per-institute client into the single-record payment-link route

**Files:**
- Modify: `routes/fee_route.py`
- Test: `tests/test_fee_routes.py`

**Interfaces:**
- Consumes: `build_institute_razorpay_client(institute) -> razorpay.Client | None` (Task 3).
- Behavior change: `GET /fee/record/{record_id}/payment-link` now returns `503` if the record's institute hasn't connected Razorpay, instead of silently using the platform's global client.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_fee_routes.py`, after the last test in the file (`test_get_fee_structure_returns_404_when_not_set`):

```python
# ─── GET /fee/record/{record_id}/payment-link ─────────────────────────────────


async def test_get_payment_link_returns_503_when_institute_not_connected(client):
    from models.enrollment_base import EnrollmentSchema
    from models.institute_base import RazorpayStatus

    teacher_id = uuid4()
    owner_svc, institute_svc, batch = _setup_owner_institute_batch(teacher_id)

    enrollment = MagicMock(spec=EnrollmentSchema)
    enrollment.id = 20
    enrollment.batch_id = 5

    institute = _make_institute(institute_id=10)
    institute.razorpay_status = RazorpayStatus.NOT_CONNECTED
    institute.razorpay_key_id = None
    institute.razorpay_key_secret_encrypted = None
    institute_svc.institute_repo = MagicMock()
    institute_svc.institute_repo.get_by_id = AsyncMock(return_value=institute)

    fee_svc = MagicMock(spec=FeeService)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    with patch("routes.fee_route._verify_batch_belongs_to_institute", new=AsyncMock(return_value=batch)):
        with patch("routes.fee_route.select"):
            fee_result = MagicMock()
            fee_result.scalar_one_or_none.return_value = _make_fee_record()
            enroll_result = MagicMock()
            enroll_result.scalar_one_or_none.return_value = enrollment

            mock_db = MagicMock()
            mock_db.execute = AsyncMock(side_effect=[fee_result, enroll_result])

            from db.session import get_db

            app.dependency_overrides[get_db] = lambda: mock_db

            resp = await client.get(
                "/fee/record/1/payment-link",
                headers={"authorization": "Bearer test-token"},
            )

    app.dependency_overrides.clear()
    assert resp.status_code == 503


async def test_get_payment_link_success_when_institute_connected(client):
    from models.enrollment_base import EnrollmentSchema
    from models.institute_base import RazorpayStatus

    teacher_id = uuid4()
    owner_svc, institute_svc, batch = _setup_owner_institute_batch(teacher_id)

    enrollment = MagicMock(spec=EnrollmentSchema)
    enrollment.id = 20
    enrollment.batch_id = 5

    institute = _make_institute(institute_id=10)
    institute.razorpay_status = RazorpayStatus.CONNECTED
    institute.razorpay_key_id = "rzp_live_abc"
    institute.razorpay_key_secret_encrypted = "enc-blob"
    institute_svc.institute_repo = MagicMock()
    institute_svc.institute_repo.get_by_id = AsyncMock(return_value=institute)

    fee_svc = MagicMock(spec=FeeService)
    fee_svc.generate_payment_link = AsyncMock(
        return_value={
            "record_id": 1,
            "payment_link": "https://rzp.io/i/test",
            "amount_pending": Decimal("1500.00"),
            "month": date(2026, 5, 1),
        }
    )

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    with patch("routes.fee_route._verify_batch_belongs_to_institute", new=AsyncMock(return_value=batch)):
        with patch("routes.fee_route.build_institute_razorpay_client", return_value=MagicMock()):
            with patch("routes.fee_route.select"):
                fee_result = MagicMock()
                fee_result.scalar_one_or_none.return_value = _make_fee_record()
                enroll_result = MagicMock()
                enroll_result.scalar_one_or_none.return_value = enrollment

                mock_db = MagicMock()
                mock_db.execute = AsyncMock(side_effect=[fee_result, enroll_result])

                from db.session import get_db

                app.dependency_overrides[get_db] = lambda: mock_db

                resp = await client.get(
                    "/fee/record/1/payment-link",
                    headers={"authorization": "Bearer test-token"},
                )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["payment_link"] == "https://rzp.io/i/test"
```

Note: `_make_institute` already exists near the top of `tests/test_fee_routes.py` (returns a `MagicMock(spec=InstituteSchema)`); these tests reuse it and then override the `razorpay_*` attributes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fee_routes.py -v -k payment_link`
Expected: FAIL — the 503 test fails because today's route always succeeds via the global client; the 200 test fails because `routes.fee_route.build_institute_razorpay_client` doesn't exist yet to patch.

- [ ] **Step 3: Update the route**

In `routes/fee_route.py`, replace the import:

```python
from clients.razorpay_client import get_razorpay_client
```

with:

```python
from clients.razorpay_client import build_institute_razorpay_client
```

Then find, in `get_payment_link`:

```python
    await _verify_batch_belongs_to_institute(db, enrollment.batch_id, institute_id)

    try:
        razorpay_client = get_razorpay_client()
        result = await fee_service.generate_payment_link(
            db=db,
            record_id=record_id,
            razorpay_client=razorpay_client,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to generate payment link — check logs"
        )

    return result
```

Replace with:

```python
    await _verify_batch_belongs_to_institute(db, enrollment.batch_id, institute_id)

    institute = await institute_service.institute_repo.get_by_id(db, institute_id)
    razorpay_client = build_institute_razorpay_client(institute) if institute else None
    if razorpay_client is None:
        raise HTTPException(
            status_code=503,
            detail="Razorpay not connected for this institute — connect it in Owner → Payouts first",
        )

    try:
        result = await fee_service.generate_payment_link(
            db=db,
            record_id=record_id,
            razorpay_client=razorpay_client,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to generate payment link — check logs"
        )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fee_routes.py -v`
Expected: All tests PASS, including the two new ones.

- [ ] **Step 5: Run the full backend test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add routes/fee_route.py tests/test_fee_routes.py
git commit -m "feat(fees): use institute's own Razorpay account for single payment links"
```

---

### Task 5: Backfill query + service method

**Files:**
- Modify: `repositories/fee_repository.py`
- Modify: `services/fee_service.py`
- Test: `tests/test_fee_repository.py` (new file)
- Test: `tests/test_fee_service.py`

**Interfaces:**
- Consumes: `build_institute_razorpay_client` (Task 3), `FeeService.generate_payment_link` (existing).
- Produces: `FeeRepository.get_records_missing_payment_link_for_month(db, month, institute_id=None) -> list[tuple[FeeRecordSchema, InstituteSchema]]` and `FeeService.backfill_missing_payment_links(db, institute_id=None, month=None) -> dict` — both consumed by Task 6 (admin route) and Task 7 (scheduler).
  - `backfill_missing_payment_links` return shape: `{"month": date, "checked": int, "generated": int, "skipped_no_razorpay": int, "failed": int, "errors": list[dict]}`.

- [ ] **Step 1: Write the failing repository tests**

Create `tests/test_fee_repository.py`:

```python
"""
Integration tests for FeeRepository.get_records_missing_payment_link_for_month.

Seeds real data in the test DB (sqlite in-memory) so the join across
Enrollment -> Batch -> Institute is actually exercised, not mocked.
"""

import secrets
import string
from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from models.batch_base import BatchSchema, BatchStatus
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.student_base import StudentSchema
from repositories.fee_repository import FeeRepository


def _join_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def _seed_institute(db, name="Test Institute"):
    owner = OwnerSchema(
        name="Owner", phone_number=f"9{uuid4().int % 10**9:09d}", teacher_id=uuid4()
    )
    db.add(owner)
    await db.flush()

    institute = InstituteSchema(owner_id=owner.id, name=name, city="Delhi", join_code=_join_code())
    db.add(institute)
    await db.flush()
    return institute


async def _seed_fee_record(db, institute, month, payment_link=None, status=FeeStatus.NOT_PAID):
    batch = BatchSchema(
        institute_id=institute.id,
        name="Maths Batch",
        subject="Maths",
        start_time=time(9, 0),
        end_time=time(10, 0),
        days_of_week=["MON"],
        max_capacity=30,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )
    db.add(batch)
    await db.flush()

    student = StudentSchema(name="Student", institute_id=institute.id)
    db.add(student)
    await db.flush()

    enrollment = EnrollmentSchema(student_id=student.id, batch_id=batch.id, due_day=1, is_active=True)
    db.add(enrollment)
    await db.flush()

    fee_record = FeeRecordSchema(
        enrollment_id=enrollment.id,
        month=month,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=status,
        payment_link=payment_link,
    )
    db.add(fee_record)
    await db.commit()
    return fee_record


async def test_returns_records_missing_payment_link_for_the_month(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    record = await _seed_fee_record(db_session, institute, date(2026, 6, 1))

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert len(rows) == 1
    assert rows[0][0].id == record.id
    assert rows[0][1].id == institute.id


async def test_excludes_records_that_already_have_a_payment_link(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    await _seed_fee_record(
        db_session, institute, date(2026, 6, 1), payment_link="https://rzp.io/i/existing"
    )

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert rows == []


async def test_excludes_fully_paid_records(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    await _seed_fee_record(db_session, institute, date(2026, 6, 1), status=FeeStatus.FULLY_PAID)

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert rows == []


async def test_excludes_records_from_a_different_month(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    await _seed_fee_record(db_session, institute, date(2026, 5, 1))

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert rows == []


async def test_institute_id_filter_scopes_to_one_institute(db_session):
    repo = FeeRepository()
    institute_a = await _seed_institute(db_session, name="Institute A")
    institute_b = await _seed_institute(db_session, name="Institute B")
    record_a = await _seed_fee_record(db_session, institute_a, date(2026, 6, 1))
    await _seed_fee_record(db_session, institute_b, date(2026, 6, 1))

    rows = await repo.get_records_missing_payment_link_for_month(
        db_session, date(2026, 6, 1), institute_id=institute_a.id
    )

    assert len(rows) == 1
    assert rows[0][0].id == record_a.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fee_repository.py -v`
Expected: FAIL — `AttributeError: 'FeeRepository' object has no attribute 'get_records_missing_payment_link_for_month'`.

- [ ] **Step 3: Implement the repository method**

In `repositories/fee_repository.py`, add this method at the end of the `# ── FeeRecord ──` section (after `update_payment_link`):

```python
    async def get_records_missing_payment_link_for_month(
        self, db: AsyncSession, month: date, institute_id: int | None = None
    ):
        """Fee records for a month with no payment link yet, joined to their institute.

        Excludes FULLY_PAID records (no link is needed once a fee is settled) and
        records that already have a link. Used by the payment-link backfill job
        and its manual admin endpoint.
        """
        from models.batch_base import BatchSchema
        from models.enrollment_base import EnrollmentSchema
        from models.institute_base import InstituteSchema

        query = (
            select(FeeRecordSchema, InstituteSchema)
            .join(EnrollmentSchema, FeeRecordSchema.enrollment_id == EnrollmentSchema.id)
            .join(BatchSchema, EnrollmentSchema.batch_id == BatchSchema.id)
            .join(InstituteSchema, BatchSchema.institute_id == InstituteSchema.id)
            .where(
                FeeRecordSchema.month == month,
                FeeRecordSchema.payment_link.is_(None),
                FeeRecordSchema.status != FeeStatus.FULLY_PAID,
            )
        )
        if institute_id is not None:
            query = query.where(InstituteSchema.id == institute_id)

        result = await db.execute(query)
        return [(row[0], row[1]) for row in result.all()]
```

- [ ] **Step 4: Run repository tests to verify they pass**

Run: `uv run pytest tests/test_fee_repository.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Write the failing service tests**

In `tests/test_fee_service.py`, change the top import line from:

```python
from datetime import date, datetime
```

to:

```python
from datetime import date, datetime, timedelta
```

Then append this section at the end of the file:

```python
# ---------------------------------------------------------------------------
# backfill_missing_payment_links
# ---------------------------------------------------------------------------


def _make_backfill_institute(institute_id=10, status=None):
    from models.institute_base import InstituteSchema, RazorpayStatus

    i = MagicMock(spec=InstituteSchema)
    i.id = institute_id
    i.razorpay_status = status or RazorpayStatus.CONNECTED
    i.razorpay_key_id = "rzp_live_abc"
    i.razorpay_key_secret_encrypted = "enc-blob"
    return i


async def test_backfill_generates_links_for_connected_institute():
    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute()
    record1 = _make_fee_record(record_id=1)
    record2 = _make_fee_record(record_id=2)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(record1, institute), (record2, institute)]
    )
    svc.generate_payment_link = AsyncMock(return_value={})

    with patch("clients.razorpay_client.build_institute_razorpay_client", return_value=MagicMock()):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["checked"] == 2
    assert summary["generated"] == 2
    assert summary["skipped_no_razorpay"] == 0
    assert summary["failed"] == 0
    assert svc.generate_payment_link.call_count == 2


async def test_backfill_skips_institutes_without_razorpay_connected():
    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute()
    record1 = _make_fee_record(record_id=1)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(record1, institute)]
    )
    svc.generate_payment_link = AsyncMock()

    with patch("clients.razorpay_client.build_institute_razorpay_client", return_value=None):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["skipped_no_razorpay"] == 1
    assert summary["generated"] == 0
    svc.generate_payment_link.assert_not_called()


async def test_backfill_counts_failures_without_stopping_the_batch():
    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute()
    record1 = _make_fee_record(record_id=1)
    record2 = _make_fee_record(record_id=2)

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[(record1, institute), (record2, institute)]
    )
    svc.generate_payment_link = AsyncMock(side_effect=[RuntimeError("razorpay down"), {}])

    with patch("clients.razorpay_client.build_institute_razorpay_client", return_value=MagicMock()):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["failed"] == 1
    assert summary["generated"] == 1
    assert summary["errors"] == [{"record_id": 1, "error": "razorpay down"}]


async def test_backfill_defaults_month_to_last_calendar_month():
    svc = FeeService()
    db = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(return_value=[])

    today = date.today()
    first_of_this_month = today.replace(day=1)
    expected_month = (first_of_this_month - timedelta(days=1)).replace(day=1)

    summary = await svc.backfill_missing_payment_links(db=db, institute_id=None, month=None)

    svc.fee_repo.get_records_missing_payment_link_for_month.assert_called_once_with(
        db, expected_month, None
    )
    assert summary["month"] == expected_month


async def test_backfill_passes_institute_id_filter_through():
    svc = FeeService()
    db = MagicMock()

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(return_value=[])

    await svc.backfill_missing_payment_links(db=db, institute_id=42, month=date(2026, 6, 1))

    svc.fee_repo.get_records_missing_payment_link_for_month.assert_called_once_with(
        db, date(2026, 6, 1), 42
    )
```

- [ ] **Step 6: Run service tests to verify they fail**

Run: `uv run pytest tests/test_fee_service.py -v -k backfill`
Expected: FAIL — `AttributeError: 'FeeService' object has no attribute 'backfill_missing_payment_links'`.

- [ ] **Step 7: Implement the service method**

In `services/fee_service.py`, update the top imports from:

```python
import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema
from repositories.fee_repository import FeeRepository
```

to:

```python
import enum
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.fee_structure_base import FeeStructureSchema
from repositories.fee_repository import FeeRepository
```

(this matches `ruff`'s `I` import-sorting rule — stdlib, then third-party, then first-party — the same grouping Task 1 already established).

Then add a module-level helper function right after the `PaymentMethod` enum definition (before `class FeeService:`):

```python
def _first_of_last_month() -> date:
    today = date.today()
    first_of_this_month = today.replace(day=1)
    return (first_of_this_month - timedelta(days=1)).replace(day=1)
```

Finally, add the new method to `FeeService`, right after `generate_payment_link` (before `def get_fee_service`):

```python
    async def backfill_missing_payment_links(
        self,
        db: AsyncSession,
        institute_id: int | None = None,
        month: date | None = None,
    ) -> dict:
        """Generate payment links for last month's fee records that don't have one yet.

        Only institutes with a connected Razorpay account are eligible — others are
        counted under skipped_no_razorpay. A failure generating one record's link is
        logged and counted under failed; it does not stop the rest of the batch.
        """
        from clients.razorpay_client import build_institute_razorpay_client

        if month is None:
            month = _first_of_last_month()

        rows = await self.fee_repo.get_records_missing_payment_link_for_month(
            db, month, institute_id
        )

        by_institute = defaultdict(list)
        institutes_by_id = {}
        for record, institute in rows:
            by_institute[institute.id].append(record)
            institutes_by_id[institute.id] = institute

        summary = {
            "month": month,
            "checked": len(rows),
            "generated": 0,
            "skipped_no_razorpay": 0,
            "failed": 0,
            "errors": [],
        }

        for inst_id, records in by_institute.items():
            institute = institutes_by_id[inst_id]
            razorpay_client = build_institute_razorpay_client(institute)
            if razorpay_client is None:
                summary["skipped_no_razorpay"] += len(records)
                continue

            for record in records:
                try:
                    await self.generate_payment_link(
                        db=db, record_id=record.id, razorpay_client=razorpay_client
                    )
                    summary["generated"] += 1
                except Exception as e:
                    logger.error(f"Failed to backfill payment link for FeeRecord {record.id}: {e}")
                    summary["failed"] += 1
                    summary["errors"].append({"record_id": record.id, "error": str(e)})

        return summary
```

- [ ] **Step 8: Run service tests to verify they pass**

Run: `uv run pytest tests/test_fee_service.py -v`
Expected: All tests PASS.

- [ ] **Step 9: Run the full backend test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 10: Commit**

```bash
git add repositories/fee_repository.py services/fee_service.py tests/test_fee_repository.py tests/test_fee_service.py
git commit -m "feat(fees): add payment-link backfill query and service method"
```

---

### Task 6: Admin backfill endpoint

**Files:**
- Create: `routes/requests/backfill_payment_links_request.py`
- Create: `routes/responses/backfill_payment_links_response.py`
- Create: `routes/admin_route.py`
- Modify: `config.py`
- Modify: `app.py`
- Test: `tests/test_admin_routes.py` (new file)

**Interfaces:**
- Consumes: `FeeService.backfill_missing_payment_links` (Task 5).
- Produces: `POST /admin/backfill-payment-links`, protected by header `X-Admin-Secret` matching `Settings.admin_backfill_secret`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_routes.py`:

```python
"""
Tests for routes/admin_route.py — the manual payment-link backfill endpoint.

Auth here is a static secret header (X-Admin-Secret), not owner JWT — this
endpoint operates across institutes, not on behalf of one logged-in owner.
All service calls are mocked.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from services.fee_service import FeeService, get_fee_service


async def test_backfill_requires_admin_secret_header(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = "s3cr3t"

        resp = await client.post("/admin/backfill-payment-links", json={})

    assert resp.status_code == 401


async def test_backfill_rejects_wrong_admin_secret(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = "s3cr3t"

        resp = await client.post(
            "/admin/backfill-payment-links",
            json={},
            headers={"X-Admin-Secret": "wrong"},
        )

    assert resp.status_code == 401


async def test_backfill_returns_503_when_not_configured(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = None

        resp = await client.post(
            "/admin/backfill-payment-links",
            json={},
            headers={"X-Admin-Secret": "anything"},
        )

    assert resp.status_code == 503


async def test_backfill_succeeds_with_correct_secret_and_returns_summary(client):
    from app import app

    fee_svc = MagicMock(spec=FeeService)
    fee_svc.backfill_missing_payment_links = AsyncMock(
        return_value={
            "month": date(2026, 6, 1),
            "checked": 3,
            "generated": 2,
            "skipped_no_razorpay": 1,
            "failed": 0,
            "errors": [],
        }
    )
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/backfill-payment-links",
                json={},
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["generated"] == 2
    _, kwargs = fee_svc.backfill_missing_payment_links.call_args
    assert kwargs["institute_id"] is None
    assert kwargs["month"] is None


async def test_backfill_passes_institute_id_from_request_body(client):
    from app import app

    fee_svc = MagicMock(spec=FeeService)
    fee_svc.backfill_missing_payment_links = AsyncMock(
        return_value={
            "month": date(2026, 6, 1),
            "checked": 0,
            "generated": 0,
            "skipped_no_razorpay": 0,
            "failed": 0,
            "errors": [],
        }
    )
    app.dependency_overrides[get_fee_service] = lambda: fee_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/backfill-payment-links",
                json={"institute_id": 42},
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    _, kwargs = fee_svc.backfill_missing_payment_links.call_args
    assert kwargs["institute_id"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_admin_routes.py -v`
Expected: FAIL — `404 Not Found` for all requests (route doesn't exist yet), or `ModuleNotFoundError` for `routes.admin_route`.

- [ ] **Step 3: Add admin_backfill_secret to config**

In `config.py`, add a field to `Settings`, right after the new `frontend_base_url` field from Task 1:

```python
    frontend_base_url: str = "https://batchbook.in"
    admin_backfill_secret: str | None = None
```

- [ ] **Step 4: Create the request/response schemas**

Create `routes/requests/backfill_payment_links_request.py`:

```python
from pydantic import BaseModel


class BackfillPaymentLinksRequest(BaseModel):
    institute_id: int | None = None
```

Create `routes/responses/backfill_payment_links_response.py`:

```python
from datetime import date

from pydantic import BaseModel


class BackfillPaymentLinksResponse(BaseModel):
    month: date
    checked: int
    generated: int
    skipped_no_razorpay: int
    failed: int
    errors: list[dict]
```

- [ ] **Step 5: Create the admin route**

Create `routes/admin_route.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.session import get_db
from routes.requests.backfill_payment_links_request import BackfillPaymentLinksRequest
from routes.responses.backfill_payment_links_response import BackfillPaymentLinksResponse
from services.fee_service import FeeService, get_fee_service

router = APIRouter(prefix="/admin")

FeeServiceDep = Annotated[FeeService, Depends(get_fee_service)]


async def _verify_admin_secret(x_admin_secret: Annotated[str | None, Header()] = None) -> None:
    settings = get_settings()
    if not settings.admin_backfill_secret:
        raise HTTPException(
            status_code=503,
            detail="Admin backfill endpoint not configured — set ADMIN_BACKFILL_SECRET in .env",
        )
    if x_admin_secret != settings.admin_backfill_secret:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Secret header")


@router.post(
    "/backfill-payment-links",
    summary="Generate missing Razorpay payment links for last month's fee records",
    response_model=BackfillPaymentLinksResponse,
    dependencies=[Depends(_verify_admin_secret)],
)
async def backfill_payment_links(
    request: BackfillPaymentLinksRequest,
    fee_service: FeeServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """Manual trigger for the same backfill logic the daily scheduled job runs.

    Always targets last calendar month. Pass institute_id to scope the sweep to
    one institute; omit it to sweep every institute with a connected Razorpay
    account.
    """
    try:
        return await fee_service.backfill_missing_payment_links(
            db=db, institute_id=request.institute_id, month=None
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Backfill failed — check logs")
```

- [ ] **Step 6: Register the router**

In `app.py`, add the import right before `from routes.attendance_route import router as attendance_router` (`admin` sorts alphabetically before `attendance`):

```python
from routes.admin_route import router as admin_router
from routes.attendance_route import router as attendance_router
```

And register it after `app.include_router(router=attendance_router)`:

```python
app.include_router(router=attendance_router)
app.include_router(router=admin_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_admin_routes.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 8: Run the full backend test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add config.py app.py routes/admin_route.py routes/requests/backfill_payment_links_request.py routes/responses/backfill_payment_links_response.py tests/test_admin_routes.py
git commit -m "feat(admin): add manual endpoint to backfill missing payment links"
```

---

### Task 7: Scheduled daily backfill job

**Files:**
- Create: `scheduler.py`
- Modify: `app.py`
- Modify: `config.py`
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml` (via `uv add`)
- Test: `tests/test_scheduler.py` (new file)

**Interfaces:**
- Consumes: `FeeService.backfill_missing_payment_links` (Task 5).
- Produces: `start_scheduler() -> AsyncIOScheduler`, `shutdown_scheduler() -> None`, gated by `Settings.enable_scheduler`.

- [ ] **Step 1: Add the apscheduler dependency**

Run: `uv add apscheduler`
Expected: `pyproject.toml` gets a new line under `dependencies` like `"apscheduler>=3.10.4",`, and `uv.lock` updates.

- [ ] **Step 2: Add enable_scheduler to config and disable it in tests**

In `config.py`, add a field to `Settings`, right after `admin_backfill_secret` (added in Task 6):

```python
    admin_backfill_secret: str | None = None
    enable_scheduler: bool = True
```

In `tests/conftest.py`, add this line among the existing `os.environ.setdefault(...)` calls at the top of the file:

```python
os.environ.setdefault("RAZORPAY_ENCRYPTION_KEY", "T-y7CuMZv82GDX0nnga1eU-Y4mfdPg34fVdzJv1QQ70=")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_scheduler.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scheduler'`.

- [ ] **Step 5: Implement scheduler.py**

Create `scheduler.py` in the project root (same level as `app.py`):

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 7: Wire the scheduler into app.py lifespan**

In `app.py`, update the imports — add after the last `routes.*` import (`scheduler` sorts alphabetically after `routes` in the first-party group):

```python
from routes.test_score_route import router as test_score_router
from scheduler import shutdown_scheduler, start_scheduler
```

Then replace the `lifespan` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    supabase_client.supabase = await create_client(
        get_settings().supabase_url, get_settings().supabase_key
    )
    if get_settings().enable_scheduler:
        start_scheduler()
    yield
    if get_settings().enable_scheduler:
        shutdown_scheduler()
```

- [ ] **Step 8: Run the full backend test suite**

Run: `uv run pytest -v`
Expected: All tests PASS. `ENABLE_SCHEDULER=false` (set in Step 2) means the scheduler never actually starts during the suite, so no background thread interferes with other tests.

- [ ] **Step 9: Commit**

```bash
git add scheduler.py app.py config.py tests/conftest.py tests/test_scheduler.py pyproject.toml uv.lock
git commit -m "feat(scheduler): run payment-link backfill daily via in-process APScheduler"
```

---

### Task 8: Submodule pointer bump + final verification

**Files:**
- Modify: `batchbookui` (submodule pointer only — commit the pointer, not the files)
- Modify: `.env.example` if one exists, else skip (see Step 1)

**Interfaces:**
- Consumes: nothing new — this task just finalizes and verifies everything from Tasks 1–7.

- [ ] **Step 1: Check for an .env.example file to document the new vars**

Run: `ls -la /Users/bedantsharma/PycharmProjects/BatchBook/.env.example 2>/dev/null || echo "no .env.example"`

If it exists, add these three lines to it (matching its existing style):

```
FRONTEND_BASE_URL=https://batchbook.in
ADMIN_BACKFILL_SECRET=
ENABLE_SCHEDULER=true
```

If it doesn't exist, skip this step — there's no example file convention to maintain in this repo.

- [ ] **Step 2: Bump the batchbookui submodule pointer**

Task 2 already pushed the frontend commit directly to `batchbookui`'s `origin/master`. Now point the parent repo at it:

```bash
git add batchbookui
git status
```

Confirm `git status` shows only `batchbookui` staged (the pointer), not a directory listing of individual frontend files — that confirms the submodule pointer update is staged correctly, not its contents.

- [ ] **Step 3: Run the full backend test suite one more time**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Run the full frontend test suite one more time**

Run: `cd batchbookui && npx vitest run && cd ..`
Expected: All tests PASS.

- [ ] **Step 5: Run ruff to confirm lint/format cleanliness**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors. If `ruff format --check` reports files needing formatting, run `uv run ruff format .`, review the diff, and re-run both checks.

- [ ] **Step 6: Commit the submodule pointer bump**

```bash
git commit -m "chore: bump batchbookui submodule to include payment success page"
```

- [ ] **Step 7: Final review of the full branch diff**

Run: `git log --oneline master..HEAD` and `git diff master...HEAD --stat`
Confirm the diff only touches the files listed across Tasks 1–7 plus the submodule pointer — nothing unexpected got swept in.

---

## Self-Review Notes

- **Spec coverage:** Section 1 (callback + success page) → Tasks 1–2. Section 2 (per-institute client) → Tasks 3–4. Section 3 (backfill logic) → Task 5. Section 4 (scheduler + admin endpoint) → Tasks 6–7. New env vars → folded into the tasks that need them (Task 1: `FRONTEND_BASE_URL`, Task 6: `ADMIN_BACKFILL_SECRET`, Task 7: `ENABLE_SCHEDULER`) per the spec's testing plan. Submodule pointer bump + final verification → Task 8.
- **Type consistency checked:** `build_institute_razorpay_client(institute) -> razorpay.Client | None` (Task 3) is called identically in Task 4 (route) and Task 5 (service). `backfill_missing_payment_links(db, institute_id=None, month=None) -> dict` (Task 5) is called identically in Task 6 (admin route, `month=None` always) and Task 7 (scheduler, no institute_id/month args at all — relies on both defaulting). `get_records_missing_payment_link_for_month(db, month, institute_id=None)` (Task 5) — positional argument order matches between the repository implementation and every test's `assert_called_once_with`.
- **No placeholders:** every step has complete, runnable code — no TBD/TODO markers.
