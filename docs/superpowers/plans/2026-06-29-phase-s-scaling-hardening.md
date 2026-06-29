# Phase S — Pre-Scaling Hardening

Do before pushing past ~2–3k active users. Ordered by impact.

## Global Constraints

- Package manager: `uv` — always `uv add <pkg>` and `uv run <cmd>`
- Linter: `ruff`, line-length 100, Python 3.14 target
- Test runner: `uv run pytest` — async mode is `auto`, tests in `tests/`
- Do NOT edit Alembic migration files by hand; create new migrations with `uv run alembic revision --autogenerate`
- Never use `pip` or `python` directly
- All new config values go in `config.py` Settings class AND `.env`

---

### Task 1 — Replace `supabase.auth.get_user()` with local JWT verification

**Files to touch:** `services/auth_service.py`, `config.py`, `tests/test_auth_service.py`

**Why:** `services/auth_service.py` calls `await supabase.auth.get_user(token)` on **every single authenticated request** — a network round-trip to Supabase Auth for every `/owner/me`, `/batch`, `/fee`, `/attendance` call. At scale this adds latency, creates an availability dependency on Supabase Auth, and can hit rate limits.

**Fix:** Verify the JWT locally using the Supabase JWT secret (HS256). Supabase signs JWTs with a project secret. Decode + verify signature + check `exp`/`aud` in-process; pull the user id from the `sub` claim.

**Steps:**

1. `uv add pyjwt` (if not already present — check `pyproject.toml` first)
2. Add `supabase_jwt_secret: str` to `Settings` in `config.py`
3. In `services/auth_service.py`, replace the body of `get_current_user_id`:
   - Strip `"Bearer "` prefix from `authorization`
   - Call `jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")`
   - Return `UUID(payload["sub"])`
   - Catch `jwt.InvalidTokenError` and raise `HTTPException(status_code=401, detail="Invalid token")`
   - The `supabase: AsyncClient` parameter can remain in the signature for now (it is injected by FastAPI Depends; removing it would require updating all callers — leave it, just don't call it)
4. In `tests/test_auth_service.py`, write/update tests:
   - valid token (signed with known secret) → returns correct UUID
   - expired token → raises 401 HTTPException
   - tampered signature → raises 401 HTTPException
   - missing/malformed Bearer prefix → raises 401 HTTPException

**Important:** The function signature `async def get_current_user_id(supabase: AsyncClient, authorization: str) -> UUID` must remain unchanged — every route uses it via FastAPI Depends. Only the body changes.

**Test to run:** `uv run pytest tests/test_auth_service.py -v`

---

### Task 2 — Config-driven SQLAlchemy `echo` + explicit connection pool config

**Files to touch:** `db/session.py`, `config.py`

**Why:** `db/session.py` has `echo=True` hardcoded, which logs **every SQL statement** in production — floods logs and adds I/O overhead. Additionally there is no explicit pool config, which means stale connections are not recovered and pool behavior is undefined.

**Steps:**

1. Add to `config.py` Settings class:
   - `db_echo: bool = False`
   - `db_pool_size: int = 5`
   - `db_max_overflow: int = 10`
   - `db_pool_recycle: int = 1800`

2. Update `db/session.py` `create_async_engine(...)` call:
   - Replace `echo=True` with `echo=get_settings().db_echo`
   - Add `pool_size=get_settings().db_pool_size`
   - Add `max_overflow=get_settings().db_max_overflow`
   - Add `pool_pre_ping=True`
   - Add `pool_recycle=get_settings().db_pool_recycle`

3. No new tests needed — engine construction is tested implicitly by the existing test suite (which uses a different DB via dependency override). Verify `uv run pytest -q` still passes (276 tests, 1 skipped).

**Note on Supavisor (Task S.2 from roadmap):** The full Supavisor switch (changing `DATABASE_URL` to port 6543 and adding `statement_cache_size=0`) requires knowing the actual Supabase project's pooler URL, which is an environment variable change the owner configures in Render. Add a comment in `session.py` explaining what to change when enabling Supavisor, but do NOT hardcode port numbers or Supavisor-specific connect_args — those should only be set if `DATABASE_URL` is the pooler URL (transaction mode). The code-level change here is just the pool config + echo fix.

---

### Task 3 — Instrument WhatsApp send logging in `notification_service.py`

**Files to touch:** `services/notification_service.py`

**Why:** WhatsApp is the only BatchBook cost that scales linearly with users. To watch the cost lever (Task S.5 from roadmap), every successful send needs to be logged with enough structured data to answer: how many messages per student per month?

**Steps:**

1. After each successful `send_template_message(...)` call in `notification_service.py`, add a `logger.info(...)` log line with these fields:
   - `template_name` (e.g. `"fee_reminder"`)
   - `student_name` where available (pass it through if not already available in scope)
   - `parent_phone` (last 4 digits only — do NOT log the full phone number)
   - `status="sent"`

   Use this format:
   ```python
   logger.info(
       "[WhatsApp] sent template={template} phone=****{phone_suffix} student={student}",
       template=template_name,
       phone_suffix=parent_phone[-4:],
       student=student_name,
   )
   ```

2. The existing error-path `logger.error(...)` calls already exist — do not change them, just add the success-path info logs.

3. There are 4 notification functions: `send_enrollment_invite`, `send_fee_reminder`, `send_fee_receipt`, `send_absence_alert`. Add success logging to all 4 after their respective `await send_template_message(...)` calls (inside the `try` block, after the await).

4. For `send_absence_alert`, `student_name` is not in the current signature — do NOT add it to the signature (would require updating all callers). Use a placeholder: `student=f"enrollment:{enrollment_id}"` for that one function only.

5. Run `uv run pytest -q` to confirm nothing is broken.

---

### Task 4 — Document Render redundancy & worker tuning in-code

**Files to touch:** `Dockerfile` (prod CMD comment only), `db/session.py` (comment), a new `docs/render-scaling-playbook.md`

**Why (Task S.4 from roadmap):** The Render-side steps (2nd instance, Standard plan, in-memory state check) cannot be done via code, but they need to be documented so the owner can act on them when the time comes. The code should reflect the current configuration and what to change when scaling.

**Steps:**

1. In `Dockerfile`, update the prod CMD comment to clarify the worker tuning rule:
   ```dockerfile
   # 2 workers on Render Starter (1 vCPU). Bump to 4 on Standard (2 vCPU).
   CMD ["uv", "run", "uvicorn", "app:app", \
        "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
   ```

2. In `db/session.py`, add a comment block above `create_async_engine(...)` explaining the Supavisor switch:
   ```python
   # When switching DATABASE_URL to Supabase's Supavisor transaction-mode pooler
   # (port 6543), also add: connect_args={"statement_cache_size": 0}
   # to avoid "prepared statement already exists" errors under load.
   ```

3. Create `docs/render-scaling-playbook.md` with:
   - When to scale (milestones: 500 active users, 2k, 5k)
   - Render Starter → Standard → Pro plan progression
   - How to add a 2nd instance (zero-downtime deploys)
   - Supavisor switch instructions (change DATABASE_URL port + add connect_args)
   - Statement that the app holds no per-instance in-memory state (auth is stateless JWT after S.1)

4. Run `uv run pytest -q` to confirm nothing broken.
