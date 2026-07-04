## PHASE S — Pre-Scaling Hardening 🟡 PARTIAL

> **When to do this:** Not urgent at current scale (single-digit/low-hundreds of users). These are the changes that must land **before** you push past ~2–3k active users. At 10k students the app architecturally holds, but these four items are where it breaks first if left as-is. Ordered by impact.

---

### Task S.1 — Replace `supabase.auth.get_user()` with local JWT verification ✅ DONE

**Why this is critical at scale:** Every authenticated request previously made a network round-trip to Supabase Auth. At scale this adds latency, creates an availability dependency, and can hit rate limits.

**What was discovered:** This project uses **asymmetric ES256/P-256 keys** (not the shared HS256 secret). Supabase exposes the public key at `{supabase_url}/auth/v1/.well-known/jwks.json`.

- [x] `uv add "pyjwt[cryptography]"` for ES256 support
- [x] Fetch + cache EC public key from Supabase JWKS endpoint on first request (`_get_public_key`)
- [x] Verify tokens with `jwt.decode(token, public_key, algorithms=["ES256"], audience="authenticated")`
- [x] JWKS fetch failures → 503; token failures → 401
- [x] No `SUPABASE_JWT_SECRET` env var needed — public key fetched automatically via existing `SUPABASE_URL`
- [x] 5 tests: valid token, expired, tampered, malformed Bearer, JWKS fetch failure (503)

**PRs:** #40 (Phase S base) + #41 (ES256 JWKS fix — pending merge)

**Verified by:** _(pending smoke test on batchbook.in after PR #41 merges)_

---

### Task S.2 — Set explicit SQLAlchemy pool config 🟡 PARTIAL

**Why this is critical at scale:** Without explicit pool config, stale connections cause intermittent errors and connection exhaustion is undefined.

- [x] `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`, `pool_recycle=1800` added to `create_async_engine`
- [x] SQLite guard — pool params not applied to the test DB (`sqlite+aiosqlite://`)
- [x] Comment in `db/session.py` explains exactly what to add when switching to Supavisor
- [ ] **Future (Milestone 3 / ~2k+ concurrent users):** Switch `DATABASE_URL` from port 5432 → port 6543 (Supavisor transaction-mode pooler) + add `connect_args={"statement_cache_size": 0}`. See `docs/render-scaling-playbook.md` for step-by-step.

**PR:** #40

---

### Task S.3 — Turn off SQLAlchemy `echo=True` in production ✅ DONE

- [x] `echo` is now config-driven: `db_echo: bool = False` in `config.py` (default off)
- [x] Set `DB_ECHO=true` in `.env` to re-enable for local debugging

**PR:** #40

---

### Task S.4 — Render redundancy & worker tuning 🟡 PARTIAL (docs done, infra future)

- [x] Dockerfile prod CMD comment updated: "2 workers on Render Starter (1 vCPU). Bump to 4 on Standard (2 vCPU)."
- [x] `docs/render-scaling-playbook.md` created — covers scaling milestones (500/2k/5k active users), Render plan progression, 2nd instance setup, Supavisor switch, stateless-JWT confirmation
- [x] App confirmed stateless — auth is local JWT, no per-instance in-memory state
- [ ] **Future (500 active users):** Upgrade Render Starter → Standard, bump workers to 4
- [ ] **Future (2k active users):** Add 2nd Render instance for zero-downtime deploys

**PR:** #40

---

### Task S.5 — Watch the WhatsApp cost lever 🟡 PARTIAL (logging done, others guidelines)

- [x] Every successful `send_template_message()` call now logs: template name, last-4 digits of phone (PII-safe), student identifier — structured and queryable
- [ ] Prefer replying inside the free 24h service window where possible (utility templates inside an open window are free; only business-initiated ones are billed)
- [ ] Batch/dedupe reminders so you're not sending 3 separate templates where 1 would do
- [ ] India volume tiers auto-discount utility rates as monthly volume climbs — treat ₹0.15 as a ceiling, not a floor

**PR:** #40

---