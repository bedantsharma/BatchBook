# Task F.5 — Key Rotation/Revocation Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when an owner's stored Razorpay keys stop working (rotated/revoked on their own dashboard), flip that institute's payout status to `NEEDS_RECONNECT`, and give the owner a way to confirm recovery after they paste fresh keys.

**Architecture:** Two Razorpay call sites already exist that use an institute's stored credentials to generate a payment link: the manual `GET /fee/record/{id}/payment-link` route and the scheduled `FeeService.backfill_missing_payment_links`. Both wrap the Razorpay SDK call in a try/except; we add a specific catch for `razorpay.errors.BadRequestError` (the same exception the SDK raises for bad auth — already relied on in `InstituteService.connect_razorpay`'s live-credential check) that flips `Institute.razorpay_status` to `NEEDS_RECONNECT` via a new `InstituteService.flag_needs_reconnect()` method. Separately, a new `InstituteService.test_razorpay_connection()` method + `POST /owner/institute/payouts/test-connection` route lets the owner manually re-validate stored keys on demand — success flips `NEEDS_RECONNECT` back to `CONNECTED`. A "Test connection" button is added to the frontend Settings → Payouts page to call it.

**Tech Stack:** FastAPI, SQLAlchemy async, razorpay-python SDK, pytest + pytest-asyncio, React + MUI, Vitest + Testing Library.

## Global Constraints

- No new DB columns or migration — `RazorpayStatus.NEEDS_RECONNECT` already exists on `InstituteSchema` (`models/institute_base.py`).
- Auth-failure detection must only catch `razorpay.errors.BadRequestError` (the SDK's auth/bad-credential error) — never a bare `except Exception`, so a transient Razorpay outage (`ServerError`/`GatewayError`) doesn't wrongly flag a healthy institute as needing reconnect.
- `flag_needs_reconnect` and `test_razorpay_connection` must be idempotent: calling either when the institute is already in the target status must not raise or double-write.
- Run `uv run pytest -v` after every backend task; run `cd batchbookui && npm run test -- --run` (or the project's configured test command) after the frontend task. Confirm 0 failures before moving to the next task.
- Run `mcp__gitnexus__detect_changes()` before the final commit (per project CLAUDE.md) to confirm only expected symbols/flows are touched.

---

### Task 1: `InstituteService.flag_needs_reconnect` — flip status on auth failure

**Files:**
- Modify: `services/institute_service.py`
- Test: `tests/test_institute_service.py`

**Interfaces:**
- Produces: `InstituteService.flag_needs_reconnect(db: AsyncSession, institute_id: int) -> InstituteSchema | None` — returns `None` if no institute with that id exists; otherwise returns the institute (updated to `NEEDS_RECONNECT`, or unchanged if already `NEEDS_RECONNECT`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_institute_service.py` (after the `set_webhook_secret` tests, end of file):

```python
# --- flag_needs_reconnect ---


async def test_flag_needs_reconnect_updates_status(service, mock_db):
    from models.institute_base import RazorpayStatus

    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.CONNECTED
    updated = _make_institute(owner_id=4)
    updated.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.flag_needs_reconnect(mock_db, institute_id=10)

    assert result is updated
    update_mock.assert_called_once_with(
        mock_db, existing, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
    )


async def test_flag_needs_reconnect_is_noop_when_already_flagged(service, mock_db):
    from models.institute_base import RazorpayStatus

    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.flag_needs_reconnect(mock_db, institute_id=10)

    assert result is existing
    update_mock.assert_not_called()


async def test_flag_needs_reconnect_returns_none_when_institute_missing(service, mock_db):
    with patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=None)):
        result = await service.flag_needs_reconnect(mock_db, institute_id=999)

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_institute_service.py -k flag_needs_reconnect -v`
Expected: FAIL with `AttributeError: 'InstituteService' object has no attribute 'flag_needs_reconnect'`

- [ ] **Step 3: Implement `flag_needs_reconnect`**

In `services/institute_service.py`, add this method to `InstituteService` (immediately after `set_webhook_secret`, before `def get_institute_service():`):

```python
    async def flag_needs_reconnect(
        self, db: AsyncSession, institute_id: int
    ) -> InstituteSchema | None:
        """Flip an institute's payout status to NEEDS_RECONNECT after a Razorpay
        auth failure using its stored keys (rotated/revoked on the owner's own
        Razorpay dashboard).

        Idempotent: a no-op if the institute is already NEEDS_RECONNECT, so a
        second auth failure (e.g. a retried backfill sweep) doesn't re-write it.

        Returns None if no institute with this id exists, so callers (which
        already hold a live institute reference in most cases) can treat a
        vanished institute as a no-op rather than an error.
        """
        institute = await self.institute_repo.get_by_id(db, institute_id)
        if not institute:
            return None
        if institute.razorpay_status == RazorpayStatus.NEEDS_RECONNECT:
            return institute
        return await self.institute_repo.update(
            db, institute, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_institute_service.py -k flag_needs_reconnect -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add services/institute_service.py tests/test_institute_service.py
git commit -m "feat(payouts): add InstituteService.flag_needs_reconnect (Task F.5)"
```

---

### Task 2: Flip status on manual payment-link generation auth failure

**Files:**
- Modify: `routes/fee_route.py:395-407` (the `try/except` around `fee_service.generate_payment_link` in `get_payment_link`)
- Test: `tests/test_fee_routes.py`

**Interfaces:**
- Consumes: `InstituteService.flag_needs_reconnect(db, institute_id) -> InstituteSchema | None` (Task 1)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fee_routes.py` (after `test_get_payment_link_success_when_institute_connected`):

```python
async def test_get_payment_link_flags_needs_reconnect_on_razorpay_auth_failure(client):
    import razorpay

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
    institute_svc.flag_needs_reconnect = AsyncMock(return_value=institute)

    fee_svc = MagicMock(spec=FeeService)
    fee_svc.generate_payment_link = AsyncMock(
        side_effect=razorpay.errors.BadRequestError("Authentication failed")
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
    assert resp.status_code == 503
    assert "reconnect" in resp.json()["detail"].lower()
    institute_svc.flag_needs_reconnect.assert_called_once_with(mock_db, 10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fee_routes.py -k flags_needs_reconnect -v`
Expected: FAIL — currently `razorpay.errors.BadRequestError` falls into the generic `except Exception` branch and returns 500, not 503, and `flag_needs_reconnect` is never called.

- [ ] **Step 3: Implement the catch in `get_payment_link`**

In `routes/fee_route.py`, add the import at the top (after `from clients.razorpay_client import build_institute_razorpay_client`, line 11):

```python
import razorpay
```

Then replace the `try/except` block at the end of `get_payment_link` (currently lines 395-407):

```python
    try:
        result = await fee_service.generate_payment_link(
            db=db,
            record_id=record_id,
            razorpay_client=razorpay_client,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except razorpay.errors.BadRequestError:
        await institute_service.flag_needs_reconnect(db, institute_id)
        raise HTTPException(
            status_code=503,
            detail="Razorpay rejected these credentials — your keys may have been "
            "rotated or revoked. Reconnect in Settings → Payouts.",
        )
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to generate payment link — check logs"
        )

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fee_routes.py -k flags_needs_reconnect -v`
Expected: 1 passed

Then run the full fee_routes suite to confirm no regressions: `uv run pytest tests/test_fee_routes.py -v` — expect all passing.

- [ ] **Step 5: Commit**

```bash
git add routes/fee_route.py tests/test_fee_routes.py
git commit -m "feat(payouts): flag institute for reconnect on payment-link auth failure (Task F.5)"
```

---

### Task 3: Flip status on backfill auth failure, skip remaining records for that institute

**Files:**
- Modify: `services/fee_service.py:412-439` (the per-institute loop inside `backfill_missing_payment_links`)
- Test: `tests/test_fee_service.py`

**Interfaces:**
- Consumes: `InstituteService.flag_needs_reconnect(db, institute_id) -> InstituteSchema | None` (Task 1)

**Why skip remaining records instead of retrying each one:** if the stored keys are bad, every remaining record for that institute will fail identically — retrying them one-by-one just wastes time and floods the log with the same error.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fee_service.py` (after `test_backfill_counts_failures_without_stopping_the_batch`):

```python
async def test_backfill_flags_institute_and_skips_remaining_on_auth_failure():
    import razorpay

    svc = FeeService()
    db = MagicMock()

    institute = _make_backfill_institute(institute_id=10)
    other_institute = _make_backfill_institute(institute_id=20)
    record1 = _make_fee_record(record_id=1)
    record2 = _make_fee_record(record_id=2)  # same institute as record1 — must be skipped
    record3 = _make_fee_record(record_id=3)  # different institute — must still succeed

    svc.fee_repo = MagicMock()
    svc.fee_repo.get_records_missing_payment_link_for_month = AsyncMock(
        return_value=[
            (record1, institute),
            (record2, institute),
            (record3, other_institute),
        ]
    )
    svc.generate_payment_link = AsyncMock(
        side_effect=[razorpay.errors.BadRequestError("Authentication failed"), {}]
    )

    mock_institute_service = MagicMock()
    mock_institute_service.flag_needs_reconnect = AsyncMock()

    with (
        patch("clients.razorpay_client.build_institute_razorpay_client", return_value=MagicMock()),
        patch("services.institute_service.InstituteService", return_value=mock_institute_service),
    ):
        summary = await svc.backfill_missing_payment_links(
            db=db, institute_id=None, month=date(2026, 6, 1)
        )

    assert summary["generated"] == 1
    assert summary["failed"] == 2
    mock_institute_service.flag_needs_reconnect.assert_called_once_with(db, 10)
    assert svc.generate_payment_link.call_count == 2  # record2 was never attempted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fee_service.py -k flags_institute_and_skips -v`
Expected: FAIL — currently `razorpay.errors.BadRequestError` is caught by the generic `except Exception`, counted as one `failed`, and the loop continues to attempt `record2`.

- [ ] **Step 3: Implement the auth-failure branch**

In `services/fee_service.py`, add `import razorpay` to the top-level imports (after `from fastapi import BackgroundTasks`, line 6):

```python
import razorpay
```

Then replace the inner `for record in records:` loop inside `backfill_missing_payment_links` (currently lines 430-439):

```python
            for idx, record in enumerate(records):
                try:
                    await self.generate_payment_link(
                        db=db, record_id=record.id, razorpay_client=razorpay_client
                    )
                    summary["generated"] += 1
                except razorpay.errors.BadRequestError as e:
                    logger.error(
                        f"Razorpay auth failed for institute {inst_id} — flagging for "
                        f"reconnect and skipping its remaining records this sweep: {e}"
                    )
                    from services.institute_service import InstituteService

                    await InstituteService().flag_needs_reconnect(db, inst_id)
                    remaining = records[idx:]
                    summary["failed"] += len(remaining)
                    for r in remaining:
                        summary["errors"].append(
                            {"record_id": r.id, "error": "Razorpay authentication failed"}
                        )
                    break
                except Exception as e:
                    logger.error(f"Failed to backfill payment link for FeeRecord {record.id}: {e}")
                    summary["failed"] += 1
                    summary["errors"].append({"record_id": record.id, "error": str(e)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fee_service.py -k flags_institute_and_skips -v`
Expected: 1 passed

Then run the full fee_service suite: `uv run pytest tests/test_fee_service.py -v` — expect all passing (existing backfill tests still pass since they never raise `BadRequestError`).

- [ ] **Step 5: Commit**

```bash
git add services/fee_service.py tests/test_fee_service.py
git commit -m "feat(payouts): flag institute for reconnect during backfill auth failure (Task F.5)"
```

---

### Task 4: `InstituteService.test_razorpay_connection` + `POST /owner/institute/payouts/test-connection`

**Files:**
- Modify: `services/institute_service.py`
- Modify: `routes/owner_route.py`
- Test: `tests/test_institute_service.py`
- Test: `tests/test_institute_routes.py`

**Interfaces:**
- Produces: `InstituteService.test_razorpay_connection(db: AsyncSession, owner_id: int) -> InstituteSchema` — re-validates stored keys; flips `NEEDS_RECONNECT`→`CONNECTED` on success, `CONNECTED`→`NEEDS_RECONNECT` on auth failure. Raises `ValueError` if no institute exists or no credentials are saved yet. Can raise `services.crypto_service.EncryptionNotConfigured` (propagated from `decrypt_secret`).
- Produces: `POST /owner/institute/payouts/test-connection` → `RazorpayPayoutResponse` (same shape as the existing `GET`/`PATCH /owner/institute/payouts` responses).

- [ ] **Step 1: Write the failing service-layer tests**

Append to `tests/test_institute_service.py` (after the `flag_needs_reconnect` tests from Task 1):

```python
# --- test_razorpay_connection ---


async def test_test_connection_flips_needs_reconnect_to_connected_on_success(service, mock_db):
    from models.institute_base import RazorpayStatus

    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    existing.razorpay_key_id = "rzp_live_abc123"
    existing.razorpay_key_secret_encrypted = "encrypted-blob"
    updated = _make_institute(owner_id=4)
    updated.razorpay_status = RazorpayStatus.CONNECTED
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.decrypt_secret", return_value="plainsecret"),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.return_value = {"items": []}
        result = await service.test_razorpay_connection(mock_db, owner_id=4)

    assert result is updated
    mock_client_cls.assert_called_once_with(auth=("rzp_live_abc123", "plainsecret"))
    update_mock.assert_called_once_with(
        mock_db, existing, {"razorpay_status": RazorpayStatus.CONNECTED}
    )


async def test_test_connection_noop_when_already_connected_and_still_valid(service, mock_db):
    from models.institute_base import RazorpayStatus

    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.CONNECTED
    existing.razorpay_key_id = "rzp_live_abc123"
    existing.razorpay_key_secret_encrypted = "encrypted-blob"
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.decrypt_secret", return_value="plainsecret"),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.return_value = {"items": []}
        result = await service.test_razorpay_connection(mock_db, owner_id=4)

    assert result is existing
    update_mock.assert_not_called()


async def test_test_connection_flips_connected_to_needs_reconnect_on_auth_failure(service, mock_db):
    import razorpay

    from models.institute_base import RazorpayStatus

    existing = _make_institute(owner_id=4)
    existing.razorpay_status = RazorpayStatus.CONNECTED
    existing.razorpay_key_id = "rzp_live_abc123"
    existing.razorpay_key_secret_encrypted = "encrypted-blob"
    updated = _make_institute(owner_id=4)
    updated.razorpay_status = RazorpayStatus.NEEDS_RECONNECT
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
        patch("services.institute_service.decrypt_secret", return_value="plainsecret"),
        patch("services.institute_service.razorpay.Client") as mock_client_cls,
    ):
        mock_client_cls.return_value.payment.all.side_effect = razorpay.errors.BadRequestError(
            "Authentication failed"
        )
        result = await service.test_razorpay_connection(mock_db, owner_id=4)

    assert result is updated
    update_mock.assert_called_once_with(
        mock_db, existing, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
    )


async def test_test_connection_raises_when_no_institute(service, mock_db):
    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="No institute found"):
            await service.test_razorpay_connection(mock_db, owner_id=999)


async def test_test_connection_raises_when_no_credentials_saved(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.razorpay_key_id = None
    existing.razorpay_key_secret_encrypted = None

    with patch.object(service.institute_repo, "get_by_owner_id", new=AsyncMock(return_value=existing)):
        with pytest.raises(ValueError, match="No Razorpay credentials saved"):
            await service.test_razorpay_connection(mock_db, owner_id=4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_institute_service.py -k test_connection -v`
Expected: FAIL with `AttributeError: 'InstituteService' object has no attribute 'test_razorpay_connection'`

- [ ] **Step 3: Implement `test_razorpay_connection`**

In `services/institute_service.py`, add this import at the top (with the other imports, after `from repositories.institute_repository import InstituteRepository`):

```python
from services.crypto_service import decrypt_secret
```

Add this method to `InstituteService`, immediately after `flag_needs_reconnect` (from Task 1):

```python
    async def test_razorpay_connection(self, db: AsyncSession, owner_id: int) -> InstituteSchema:
        """Re-validate an institute's already-saved Razorpay keys with a live API call.

        Unlike connect_razorpay, this doesn't take new keys — it re-checks the
        ones already on file, which is exactly what's needed after an owner
        reports "reconnect" isn't clearing: confirm whether the stored keys
        actually still work before assuming a UI bug.

        Flips CONNECTED -> NEEDS_RECONNECT on an auth failure, and
        NEEDS_RECONNECT -> CONNECTED on success, so a manual "Test connection"
        click can both catch a silent rotation and confirm recovery after the
        owner pastes fresh keys via connect_razorpay.

        Raises:
            ValueError: If no institute exists for this owner, or no
                credentials have been saved yet.
        """
        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            raise ValueError("No institute found for this owner")
        if not institute.razorpay_key_id or not institute.razorpay_key_secret_encrypted:
            raise ValueError("No Razorpay credentials saved yet — connect an account first")

        secret = decrypt_secret(institute.razorpay_key_secret_encrypted)
        client = razorpay.Client(auth=(institute.razorpay_key_id, secret))
        try:
            await asyncio.to_thread(client.payment.all, {"count": 1})
        except razorpay.errors.BadRequestError:
            return await self.institute_repo.update(
                db, institute, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
            )

        if institute.razorpay_status != RazorpayStatus.CONNECTED:
            return await self.institute_repo.update(
                db, institute, {"razorpay_status": RazorpayStatus.CONNECTED}
            )
        return institute
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_institute_service.py -v`
Expected: all passing (new `test_connection` tests plus all pre-existing ones)

- [ ] **Step 5: Write the failing route tests**

Append to `tests/test_institute_routes.py` (at the end of the file, after the webhook-secret tests):

```python
# ─── POST /owner/institute/payouts/test-connection ─────────────────────────────


def _setup_institute_service_test_connection(client, result=None, error=None):
    mock_svc = MagicMock(spec=InstituteService)
    if error is not None:
        mock_svc.test_razorpay_connection = AsyncMock(side_effect=error)
    else:
        mock_svc.test_razorpay_connection = AsyncMock(return_value=result)
    from app import app

    app.dependency_overrides[get_institute_service] = lambda: mock_svc
    return mock_svc


async def test_test_connection_returns_connected_status(client):
    from models.institute_base import RazorpayStatus

    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    result = _make_institute(
        owner_id=owner.id, razorpay_status="CONNECTED", razorpay_key_id="rzp_live_abc"
    )

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service_test_connection(client, result=result)

    response = await client.post(
        "/owner/institute/payouts/test-connection",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CONNECTED"


async def test_test_connection_returns_needs_reconnect_status(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    result = _make_institute(
        owner_id=owner.id, razorpay_status="NEEDS_RECONNECT", razorpay_key_id="rzp_live_abc"
    )

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service_test_connection(client, result=result)

    response = await client.post(
        "/owner/institute/payouts/test-connection",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_RECONNECT"


async def test_test_connection_returns_404_when_no_institute(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service_test_connection(
        client, error=ValueError("No institute found for this owner")
    )

    response = await client.post(
        "/owner/institute/payouts/test-connection",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404


async def test_test_connection_returns_503_when_encryption_not_configured(client):
    from services.crypto_service import EncryptionNotConfigured

    teacher_id = uuid4()
    owner = _make_owner(teacher_id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service_test_connection(
        client, error=EncryptionNotConfigured("RAZORPAY_ENCRYPTION_KEY not set")
    )

    response = await client.post(
        "/owner/institute/payouts/test-connection",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 503
```

- [ ] **Step 6: Run route tests to verify they fail**

Run: `uv run pytest tests/test_institute_routes.py -k test_connection -v`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 7: Implement the route**

In `routes/owner_route.py`, add this route at the end of the file, after `update_razorpay_webhook_secret`:

```python
@router.post(
    "/institute/payouts/test-connection",
    summary="Re-validate the owner's saved Razorpay credentials against the live API",
    response_model=RazorpayPayoutResponse,
)
async def test_razorpay_connection(
    db: AsyncSession = Depends(get_db),
    owner_service: OwnerServiceDep = None,
    institute_service: InstituteServiceDep = None,
    teacher_id: UUID = Depends(_get_current_teacher_id),
):
    """Re-check the institute's already-saved keys (no new keys submitted here).

    Confirms whether stored credentials still authenticate — flips status to
    NEEDS_RECONNECT on failure or back to CONNECTED on success, matching the
    status transitions Task F.5 relies on elsewhere.
    """
    owner = await owner_service.get_owner_by_teacher_id(db=db, teacher_id=teacher_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner record not found")

    try:
        institute = await institute_service.test_razorpay_connection(db=db, owner_id=owner.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EncryptionNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))

    return RazorpayPayoutResponse(
        status=institute.razorpay_status.value,
        key_id=institute.razorpay_key_id,
        secret_configured=institute.razorpay_key_secret_encrypted is not None,
        webhook_configured=institute.razorpay_webhook_secret_encrypted is not None,
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_institute_routes.py -v`
Expected: all passing

Then run the full backend suite: `uv run pytest -v` — expect all passing (should be 349 pre-existing + ~13 new = ~362).

- [ ] **Step 9: Commit**

```bash
git add services/institute_service.py routes/owner_route.py tests/test_institute_service.py tests/test_institute_routes.py
git commit -m "feat(payouts): add manual Razorpay test-connection endpoint (Task F.5)"
```

---

### Task 5: Frontend — "Test connection" button on Settings → Payouts

**Files:**
- Modify: `batchbookui/src/services/ownerService.js`
- Modify: `batchbookui/src/pages/owner/SettingsPage.jsx`
- Test: `batchbookui/src/test/SettingsPage.test.jsx`

**Interfaces:**
- Consumes: `POST /owner/institute/payouts/test-connection` (Task 4)
- Produces: `testRazorpayConnection(): Promise<{status: string, key_id: string|null, secret_configured: boolean, webhook_configured: boolean}>` in `ownerService.js`

> **Reminder:** `batchbookui/` is a separate git repo (submodule) — commit inside `batchbookui/` first, then bump the pointer in `BatchBook/` per the submodule rules in this repo's CLAUDE.md.

- [ ] **Step 1: Write the failing frontend tests**

Replace the `vi.mock('../services/ownerService', ...)` block at the top of `batchbookui/src/test/SettingsPage.test.jsx` (lines 5-13) with:

```javascript
vi.mock('../services/ownerService', () => ({
  getRazorpayPayoutStatus: vi.fn(),
  saveRazorpayCredentials: vi.fn(),
  testRazorpayConnection: vi.fn(),
  getOwnerStats: vi.fn().mockResolvedValue({
    enrolled_students: 0,
    fees_collected_this_month: '0',
    avg_attendance_this_month: 0,
  }),
}));
```

And update the import on line 15:

```javascript
import { getRazorpayPayoutStatus, saveRazorpayCredentials, testRazorpayConnection } from '../services/ownerService';
```

Then add this new `describe` block at the end of the file, before the final `describe('SettingsPage — OwnerDashboard integration', ...)` block:

```javascript
describe('SettingsPage — Test connection', () => {
  it('does not show a Test connection button when not connected', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'NOT_CONNECTED', key_id: null, secret_configured: false,
    });

    render(<SettingsPage />);

    await waitFor(() => expect(getRazorpayPayoutStatus).toHaveBeenCalledOnce());
    expect(screen.queryByRole('button', { name: /test connection/i })).not.toBeInTheDocument();
  });

  it('shows a success message when the stored keys still work', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'CONNECTED', key_id: 'rzp_live_abc123', secret_configured: true,
    });
    testRazorpayConnection.mockResolvedValue({
      status: 'CONNECTED', key_id: 'rzp_live_abc123', secret_configured: true,
    });

    render(<SettingsPage />);
    await waitFor(() => screen.getByRole('button', { name: /test connection/i }));

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() => expect(testRazorpayConnection).toHaveBeenCalledOnce());
    expect(await screen.findByText(/connection is working/i)).toBeInTheDocument();
  });

  it('shows a reconnect message when the stored keys have stopped working', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'CONNECTED', key_id: 'rzp_live_abc123', secret_configured: true,
    });
    testRazorpayConnection.mockResolvedValue({
      status: 'NEEDS_RECONNECT', key_id: 'rzp_live_abc123', secret_configured: true,
    });

    render(<SettingsPage />);
    await waitFor(() => screen.getByRole('button', { name: /test connection/i }));

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));

    await waitFor(() =>
      expect(screen.getByText(/needs reconnect/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/rotated or revoked/i)).toBeInTheDocument();
  });

  it('shows an error banner when the test request itself fails', async () => {
    getRazorpayPayoutStatus.mockResolvedValue({
      status: 'CONNECTED', key_id: 'rzp_live_abc123', secret_configured: true,
    });
    testRazorpayConnection.mockRejectedValue({
      response: { data: { detail: 'No institute found for this owner' } },
    });

    render(<SettingsPage />);
    await waitFor(() => screen.getByRole('button', { name: /test connection/i }));

    fireEvent.click(screen.getByRole('button', { name: /test connection/i }));

    expect(await screen.findByText(/no institute found for this owner/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd batchbookui && npm run test -- --run SettingsPage`
Expected: FAIL — `testRazorpayConnection` doesn't exist yet, and there's no "Test connection" button.

- [ ] **Step 3: Add `testRazorpayConnection` to `ownerService.js`**

In `batchbookui/src/services/ownerService.js`, add this function immediately after `saveRazorpayCredentials` (end of file):

```javascript

/**
 * Re-validates the owner's already-saved Razorpay credentials against the
 * live API (no new keys submitted). Flips status to CONNECTED or
 * NEEDS_RECONNECT server-side depending on the result.
 * @returns {Promise<{status: string, key_id: string|null, secret_configured: boolean, webhook_configured: boolean}>}
 */
export async function testRazorpayConnection() {
  const { data } = await api.post('/owner/institute/payouts/test-connection');
  return data;
}
```

- [ ] **Step 4: Add the button + handler to `SettingsPage.jsx`**

In `batchbookui/src/pages/owner/SettingsPage.jsx`, update the import on line 14:

```javascript
import { getRazorpayPayoutStatus, saveRazorpayCredentials, testRazorpayConnection } from '../../services/ownerService';
```

Add a `testing` state next to the other `useState` calls (after `const [success, setSuccess] = useState(false);`, line 55):

```javascript
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null); // 'CONNECTED' | 'NEEDS_RECONNECT' | null
```

Add a `handleTestConnection` function after `handleSave` (after its closing `}`, currently ending at line 83):

```javascript

  async function handleTestConnection() {
    setError('');
    setSuccess(false);
    setTestResult(null);
    setTesting(true);
    try {
      const data = await testRazorpayConnection();
      setStatus(data.status);
      setTestResult(data.status);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to test Razorpay connection.');
    } finally {
      setTesting(false);
    }
  }
```

Replace the button row (currently just the single `Save` `<Button>`, lines 154-170) with a `Box` containing both buttons, and add the test-result message above it. The full replacement for that section (inside the `Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}` block, after the Key Secret `<TextField>` and before its closing `</Box>`):

```javascript
              {testResult === 'CONNECTED' && (
                <Alert severity="success" sx={{ borderRadius: '12px' }}>
                  Connection is working — your Razorpay keys are still valid.
                </Alert>
              )}
              {testResult === 'NEEDS_RECONNECT' && (
                <Alert severity="warning" sx={{ borderRadius: '12px' }}>
                  Needs Reconnect — Razorpay rejected these keys. They may have been
                  rotated or revoked on your Razorpay dashboard; paste fresh ones above.
                </Alert>
              )}
              <Box sx={{ display: 'flex', gap: 1.5 }}>
                <Button
                  variant="contained"
                  onClick={handleSave}
                  disabled={saving || !keyId || !keySecret}
                  sx={{
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
                {status !== 'NOT_CONNECTED' && (
                  <Button
                    variant="outlined"
                    onClick={handleTestConnection}
                    disabled={testing}
                    sx={{
                      fontFamily: T.sans,
                      textTransform: 'none',
                      borderRadius: '10px',
                      borderColor: T.outline,
                      color: T.fg1,
                    }}
                  >
                    {testing ? 'Testing…' : 'Test connection'}
                  </Button>
                )}
              </Box>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd batchbookui && npm run test -- --run SettingsPage`
Expected: all passing

Then run the full frontend suite: `cd batchbookui && npm run test -- --run` — expect all passing, no regressions.

- [ ] **Step 6: Commit inside the submodule, then bump the pointer**

```bash
cd batchbookui
git add src/services/ownerService.js src/pages/owner/SettingsPage.jsx src/test/SettingsPage.test.jsx
git commit -m "feat(payouts): add Test connection button to Settings (Task F.5)"
git push origin docs/a3-verified-f2-byo-razorpay
cd ..
git add batchbookui
git commit -m "chore: bump batchbookui submodule for Test connection button (Task F.5)"
```

(Push the parent-repo branch as usual once ready — this plan doesn't dictate when.)

---

### Task 6: Update PhaseF.md and final verification

**Files:**
- Modify: `PhaseF.md`

- [ ] **Step 1: Run the full backend and frontend suites one more time**

```bash
uv run pytest -v
cd batchbookui && npm run test -- --run && cd ..
```

Expected: 0 failures in both.

- [ ] **Step 2: Run `gitnexus_detect_changes` (project CLAUDE.md requirement)**

Use `mcp__gitnexus__detect_changes` with `scope: "all"` (or the default `unstaged`/`staged` depending on what's committed at this point) on the `BatchBook` repo. Confirm the affected symbols/processes match this plan's scope (`InstituteService`, `fee_route.get_payment_link`, `FeeService.backfill_missing_payment_links`, `owner_route` payouts endpoints) — no HIGH/CRITICAL risk, nothing unexpected touched.

- [ ] **Step 3: Update `PhaseF.md` Task F.5 section**

In `PhaseF.md`, replace the Task F.5 heading and checklist (currently):

```markdown
### Task F.5 — Key rotation/revocation detection

- [ ] On any `generate_payment_link()` auth failure against an institute's stored keys, flip `Institute` payout status to `Needs reconnect` and surface that state clearly in Settings
- [ ] Add a manual "Test connection" button in Settings that re-validates the stored keys on demand (reuses the Task F.2 validation call)

**Verified by:** _(pending)_
```

with:

```markdown
### Task F.5 — Key rotation/revocation detection ✅ DONE (pending PR + manual smoke test)

- [x] On any `generate_payment_link()` auth failure against an institute's stored keys, flip `Institute` payout status to `Needs reconnect` — `InstituteService.flag_needs_reconnect()`, wired into both the manual `GET /fee/record/{id}/payment-link` route and the scheduled `backfill_missing_payment_links` sweep (which also skips that institute's remaining records for the rest of the sweep instead of retrying each one against the same bad keys)
- [x] Add a manual "Test connection" button in Settings that re-validates the stored keys on demand — `InstituteService.test_razorpay_connection()` + `POST /owner/institute/payouts/test-connection`; flips `NEEDS_RECONNECT` back to `CONNECTED` on success

**Verified by:** _(code-complete 2026-07-04, not yet a PR; no manual smoke test yet against a real Razorpay test-mode key rotation)_
```

- [ ] **Step 4: Commit**

```bash
git add PhaseF.md
git commit -m "docs: mark Task F.5 code-complete in PhaseF.md"
```

---

## Self-Review Notes

- **Spec coverage:** Both PhaseF.md F.5 checklist items are covered — auth-failure detection (Tasks 2 & 3) and the manual test-connection button (Tasks 4 & 5).
- **Type consistency:** `flag_needs_reconnect` and `test_razorpay_connection` both return `InstituteSchema` (or `None`/raise), matching what Tasks 2-4 consume. `RazorpayPayoutResponse` shape is reused unchanged from the existing `GET`/`PATCH /owner/institute/payouts` endpoints.
- **Not in scope (deliberately):** Task F.6 (subscription billing) and F.7 (real end-to-end Razorpay test-mode run) are separate roadmap tasks, not touched here.
