# BatchBook — Roadmap v2 (June 2026 → Deployment)

> **How to use this file:** Read "Current Reality" first. Then pick the first unchecked item under the current phase. Phases A and B must complete before Phase C (deployment). Phase D is unblocked — Meta/WhatsApp Business verification approved 2026-06-21.

---

## Current Reality (as of June 2026)

### What actually works end-to-end
- **320 backend tests passing** — models, routes, services all solid
- **Owner dashboard**: Students, Batches, Fees, Attendance, Tests pages all built and wired to real APIs
- **Student dashboard**: Connected to real backend (not mock data)
- **Auth flows**: Owner OTP → institute check → dashboard; Parent OTP → student dashboard
- **Razorpay**: Owner can connect their own Razorpay account (Settings → Payouts); payment links now generate against that institute's own account instead of the platform's, with a success callback page for parents and an automatic + manual backfill for records missing a link — code complete, [PR #46](https://github.com/bedantsharma/BatchBook/pull/46) pending merge

### What is code-complete but never manually tested
- Phase 0 tasks (role routing, setup gate, student live data) — code merged, but "Verified by: pending" in old roadmap
- E2E Playwright specs exist (5 files) but never run against a live environment

### What is broken in production (would fail today if deployed)
- **nginx.conf only proxies `/student/*` and `/owner/*`** — fixed in Task A.1 (not yet re-verified live, since prod now runs on Render/Vercel rather than the Docker nginx stack)

### What is incomplete (code partially written or missing)
- `OwnerDashboard` header stats ("X students enrolled | ₹Y collected | Z% avg attendance") — backend `/owner/stats` exists but frontend not wired
- Student dashboard: only "Overview" tab works; Batches/Schedule/Fees tabs show greyed-out with `cursor: not-allowed`
- Student fee payment button (Razorpay link) never surfaced in student dashboard
- Attendance streak hardcoded to 0 (no backend endpoint)
- Notification count always returns 0 (no backend endpoint)
- No working `@batchbook.in` email address — domain has no MX records, so any mail sent to it bounces. Landing page footer currently links `manurishi1103@gmail.com` instead, which works fine for now. Not blocking anything; revisit if a branded inbox (e.g. via Zoho Mail free tier) becomes worth setting up.

### What is blocked on external credentials
- Meta/WhatsApp: nothing — verification (`batchbook.in`) **approved 2026-06-21**. WhatsApp Business Account is live and can send messages. Phase D ready to implement.
- ~~Razorpay live API keys~~ **RESOLVED 2026-07-06** — the pilot institute's website (`https://bedant-classes.batchbook.in`) was approved by Razorpay and live API keys were generated successfully. See `PhaseF.md` Task F.2b. Task F.8 now scopes how every *future* owner gets a qualifying website (guided self-serve first, BatchBook-generated wildcard-subdomain fallback second).

### Decision: integrate Meta Cloud API directly, skip WATI (decided 2026-06-21)

WATI (and any BSP — AiSensy, Interakt, Gupshup) is a paid wrapper (~₹2,600+/month) around the same underlying Meta WhatsApp Cloud API. Since `notification_service.py` is currently 100% stub (no real client exists yet), there's nothing to migrate — this is a clean choice of integration target before Phase D is built. All 4 message types BatchBook needs (enrollment invite, fee reminder, fee receipt, absence alert) are business-initiated **template** messages, which the Cloud API supports natively with no BSP needed:

- **Cost:** ₹0/month platform fee — pay Meta only per message sent (utility-category templates are the cheapest tier). No ₹2,600/month WATI bill.
- **Integration shape is unchanged:** still one async `httpx` client with a `send_template_message(phone, template_name, params)` method, same as the WATI plan — just pointed at `https://graph.facebook.com/v{version}/{phone_number_id}/messages` instead of WATI's endpoint.
- **One-time setup required (do before Task D.1):**
  - Generate a **permanent System User access token** in Meta Business Suite → Business Settings → System Users (scopes: `whatsapp_business_messaging`, `whatsapp_business_management`, expiry: Never) — the default token from the API testing page expires in ~1-2h and will silently break notifications in prod if used instead.
  - Note down `phone_number_id` and `WABA ID` from WhatsApp Manager.
  - New WABAs are capped at 250 unique recipients/24h (Tier 1) until usage/quality earns an upgrade — not a concern at current scale.
- Templates (`fee_reminder`, `fee_receipt`, `absence_alert`, `enrollment_invite`) are created in WhatsApp Manager under category **Utility**, not WATI's dashboard. `fee_reminder` should use a URL button pointing at the Razorpay payment link rather than embedding the raw link in text.

---

## Gap Summary Table

| Gap | Severity                                                                                                          | Blocks |
|-----|-------------------------------------------------------------------------------------------------------------------|--------|
| All institutes' fee payments settle into the platform's own Razorpay account, not the owner's | 🟢 FIXED — Task F.3, [PR #46](https://github.com/bedantsharma/BatchBook/pull/46), F.4/F.5 code-complete in [PR #48](https://github.com/bedantsharma/BatchBook/pull/48), working on F.6/F.7 | Was: onboarding any real second paying owner; regulatory exposure (RBI Payment Aggregator rules) |
| Razorpay won't issue live API keys without an approved business website (Education category), even with KYC activated | 🟢 FIXED for the pilot — Task F.2b, website approved + live keys generated 2026-07-06; Task F.8 scopes the same-gate fix for every future owner (guided self-serve site first, BatchBook wildcard-subdomain generator fallback) | Was: live API keys for the pilot institute; still relevant for every future owner in Task F.7 until F.8 is built |
| No Razorpay webhook handler — payment status is 100% manual via `PATCH /fee/record/{id}/pay` | 🟢 FIXED — Task F.4, code-complete 2026-07-03, open in [PR #48](https://github.com/bedantsharma/BatchBook/pull/48), not yet smoke-tested                                       | Was: reliable fee status, auto `fee_receipt` WATI send (Task D.2) |
| No CI/CD pipeline | 🟡 HIGH                                                                                                           | Safe deployments |
| Owner header stats not wired | 🟡 HIGH                                                                                                           | UX completeness |
| Student Batches/Schedule/Fees tabs greyed out | 🟡 HIGH                                                                                                           | Student app completeness |
| Student Razorpay payment link not surfaced | 🟡 HIGH                                                                                                           | Core value prop for parents |
| Full prod stack never smoke-tested end-to-end on `batchbook.in` | 🟡 HIGH                                                                                                           | Confidence before real users |
| Attendance streak always 0 | 🟠 MEDIUM                                                                                                         | Student UX |
| Multi-child parent has no child selector | 🟠 MEDIUM                                                                                                         | Parents with >1 child |
| E2E tests never run in CI | 🟠 MEDIUM                                                                                                         | Regression safety |
| `get_user()` network round-trip on every auth'd request; no connection pooling config; `echo=True` in prod | 🟠 MEDIUM                                                                                                         | Scaling past ~2–3k active users (Phase S) |
| No `@batchbook.in` email (no MX records) | 🟢 LOW                                                                                                            | Branded contact email only |
| No PDF fee receipt | 🟢 LOW                                                                                                            | Nice-to-have |

---

## Roadmap Overview

| Phase | Goal | Status |
|-------|------|--------|
| **A** | Fix ship-blockers — nginx, stats, student tabs | 🟡 PARTIAL — A.1 ✅ A.2 ✅ A.3 ✅ A.4 ✅ A.5 ✅ · A.1/A.2/A.4/A.5 still need a live `make prod` smoke test |
| **B** | Landing page (real marketing page + WATI website URL) | ✅ DONE — deployed at batchbookui.vercel.app |
| **C** | Deployment — hosting, domain, SSL, CI/CD | 🟡 PARTIAL — C.1 ✅ C.2 ✅ C.3 ✅ C.4 ✅ · C.5 (smoke test) remaining |
| **D** | WhatsApp notifications via Meta Cloud API direct (fee reminders, absence alerts) | ✅ DONE — D.0 ✅ D.1 ✅ D.2 ✅ D.3 ✅ · PRs open: BatchBook #33 + batchbookui #26 |
| **F** | Multi-tenant payments — owner brings their own Razorpay account (BYO keys) + per-tenant webhooks | 🟡 IN PROGRESS — F.1 ✅ F.2 ✅ F.2b ✅ F.3 ✅ F.3b ✅ F.4 ✅ F.5 ✅ (F.3/F.3b: [PR #46](https://github.com/bedantsharma/BatchBook/pull/46) pending merge; F.2/F.4/F.5: [PR #48](https://github.com/bedantsharma/BatchBook/pull/48) + [batchbookui #39](https://github.com/bedantsharma/batchbookui/pull/39), both open) · F.2b resolved 2026-07-06 (pilot website approved, live keys generated) · F.6–F.8 remaining (F.8 scoped 2026-07-06: guided self-serve website onboarding + wildcard-subdomain generator fallback for future owners) |
| **E** | Polish — multi-child, streak, receipts, E2E CI | ⬜ NOT-STARTED |
| **S** | Pre-scaling hardening — local JWT verify, connection pooling, prod DB config, Render redundancy | 🟡 PARTIAL — S.1 ✅ S.3 ✅ S.5 ✅ · S.2 pool config ✅ Supavisor switch future · S.4 docs ✅ 2nd instance future |

**Sequencing rationale:**
- Phase A first: fix what's broken before putting it in front of anyone
- Phase B second: landing page serves double duty — WATI needs a URL, owners need a place to find you
- Phase C third: now you have something worth deploying
- Phase D next up: Meta verification is approved, no external dependency left — implement whenever convenient
- **Phase F before onboarding any second real paying owner** — F.1–F.5 are code-complete ([PR #46](https://github.com/bedantsharma/BatchBook/pull/46) pending merge for F.3/F.3b; F.2/F.4/F.5 open in [PR #48](https://github.com/bedantsharma/BatchBook/pull/48) + [batchbookui #39](https://github.com/bedantsharma/batchbookui/pull/39)), closing the "money settles into your account, not theirs" gap, adding automatic webhook-based payment confirmation, and detecting rotated/revoked keys; F.6 (subscription billing) and F.7 (e2e test) remain before this is fully done.
- Phase E ongoing: polish after real users give feedback

---

## Note: every phase has a .md file related to it at the project root level read that to get the full information about that phase

---
## ⚠️ Your Actions Required Right Now
agents can write any actions required by the owner here

| Action | Unblocks |
|--------|---------|
| Merge [PR #46](https://github.com/bedantsharma/BatchBook/pull/46) and set `FRONTEND_BASE_URL` / `ADMIN_BACKFILL_SECRET` / `ENABLE_SCHEDULER` in Render's env vars | Institute-scoped payment links, success callback, and the backfill job going live (Tasks F.3–F.3b) |
| Review/merge [PR #48](https://github.com/bedantsharma/BatchBook/pull/48) + [batchbookui #39](https://github.com/bedantsharma/batchbookui/pull/39) (F.2/F.4/F.5), then manually smoke-test key-rotation detection with a real Razorpay test-mode key before building subscription billing (F.6) and the e2e test (F.7) | Safe onboarding of any real second paying owner |
| Decide who writes/tests the Tier 1 self-serve website guide (Task F.8) — Google Sites vs. Carrd walkthrough, and confirm whether Razorpay accepts a subdomain (`xyz.wixsite.com`) or requires an apex custom domain, once a real owner goes through it | Task F.8 — website onboarding for every future owner |

---

## Deployment Architecture (live)

```
batchbook.in (Vercel — CDN, auto-HTTPS)
       │
       └── React SPA, calls api.batchbook.in directly from the browser
             │
    api.batchbook.in (Render.com — always-on, $7/mo)
             │
     FastAPI + uvicorn (2 workers)
             │
      ┌──────┴──────┐
 Supabase Auth   Supabase PostgreSQL
 (OTP + JWT)     (all data)
```

> **Note on Vercel + backend calls:** `batchbookui/nginx.conf` is only used in the local Docker prod stack (`make prod`), not on Vercel. On Vercel, API calls go directly from the browser to `api.batchbook.in` — CORS in `app.py` covers this.

---


## How to Run Right Now

```bash
# Backend (Docker dev):
make dev

# Backend (no Docker):
uv run uvicorn app:app --reload --port 8000

# Frontend:
cd batchbookui && npm run dev

# Tests:
uv run pytest -v   # 320 tests

# E2E (when ready):
npx playwright test
```

---

## Status Labels

| Symbol | Meaning |
|--------|---------|
| ✅ INTEGRATED | PR merged, tests pass, manually verified |
| 🟡 PARTIAL | Some sub-tasks done, others missing |
| ⬜ NOT-STARTED | Not touched |
| 🚫 BLOCKED | Waiting on external credential or decision |
## Key Point for Future AI

The `batchbookui/` folder inside `BatchBook/` is a **git submodule**, not a regular directory. BatchBook's git only stores a pointer (a specific commit SHA) to the batchbookui repo — it does not own or track the UI files directly. Any changes inside `batchbookui/` must be committed and pushed from within that folder using its own git identity. Then the submodule pointer in BatchBook must be updated with a separate commit.