# BatchBook — Roadmap v2 (June 2026 → Deployment)

> **How to use this file:** Read "Current Reality" first. Then pick the first unchecked item under the current phase. Phases A and B must complete before Phase C (deployment). Phase D is unblocked — Meta/WhatsApp Business verification approved 2026-06-21.

---

## Current Reality (as of June 2026)

### What actually works end-to-end
- **278 backend tests passing** — models, routes, services all solid
- **Owner dashboard**: Students, Batches, Fees, Attendance, Tests pages all built and wired to real APIs
- **Student dashboard**: Connected to real backend (not mock data)
- **Auth flows**: Owner OTP → institute check → dashboard; Parent OTP → student dashboard
- **Razorpay**: Payment link endpoint implemented

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
- Nothing — Meta/WhatsApp Business verification (`batchbook.in`) **approved 2026-06-21**. WhatsApp Business Account is live and can send messages. Phase D ready to implement.

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

| Gap | Severity | Blocks |
|-----|----------|--------|
| All institutes' fee payments settle into the platform's own Razorpay account, not the owner's — single global `razorpay.Client` in `clients/razorpay_client.py` | 🔴 CRITICAL | Onboarding any real second paying owner; regulatory exposure (RBI Payment Aggregator rules) |
| No Razorpay webhook handler — payment status is 100% manual via `PATCH /fee/record/{id}/pay` | 🔴 CRITICAL | Reliable fee status, auto `fee_receipt` WATI send (Task D.2) |
| No CI/CD pipeline | 🟡 HIGH | Safe deployments |
| Owner header stats not wired | 🟡 HIGH | UX completeness |
| Student Batches/Schedule/Fees tabs greyed out | 🟡 HIGH | Student app completeness |
| Student Razorpay payment link not surfaced | 🟡 HIGH | Core value prop for parents |
| Full prod stack never smoke-tested end-to-end on `batchbook.in` | 🟡 HIGH | Confidence before real users |
| Attendance streak always 0 | 🟠 MEDIUM | Student UX |
| Multi-child parent has no child selector | 🟠 MEDIUM | Parents with >1 child |
| E2E tests never run in CI | 🟠 MEDIUM | Regression safety |
| `get_user()` network round-trip on every auth'd request; no connection pooling config; `echo=True` in prod | 🟠 MEDIUM | Scaling past ~2–3k active users (Phase S) |
| No `@batchbook.in` email (no MX records) | 🟢 LOW | Branded contact email only |
| No PDF fee receipt | 🟢 LOW | Nice-to-have |

---

## Roadmap Overview

| Phase | Goal | Status |
|-------|------|--------|
| **A** | Fix ship-blockers — nginx, stats, student tabs | 🟡 PARTIAL — A.1 ✅ A.2 ✅ A.4 ✅ A.5 ✅ · A.3 pending manual test |
| **B** | Landing page (real marketing page + WATI website URL) | ✅ DONE — deployed at batchbookui.vercel.app |
| **C** | Deployment — hosting, domain, SSL, CI/CD | 🟡 PARTIAL — C.1 ✅ C.2 ✅ C.3 ✅ C.4 ✅ · C.5 (smoke test) remaining |
| **D** | WhatsApp notifications via Meta Cloud API direct (fee reminders, absence alerts) | ✅ DONE — D.0 ✅ D.1 ✅ D.2 ✅ D.3 ✅ · PRs open: BatchBook #33 + batchbookui #26 |
| **F** | Multi-tenant payments — owner brings their own Razorpay account (BYO keys) + per-tenant webhooks | 🟢 READY — decision finalized 2026-06-23, not yet built |
| **E** | Polish — multi-child, streak, receipts, E2E CI | ⬜ NOT-STARTED |
| **S** | Pre-scaling hardening — local JWT verify, connection pooling, prod DB config, Render redundancy | 🟡 PARTIAL — S.1 ✅ S.3 ✅ S.5 ✅ · S.2 pool config ✅ Supavisor switch future · S.4 docs ✅ 2nd instance future |

**Sequencing rationale:**
- Phase A first: fix what's broken before putting it in front of anyone
- Phase B second: landing page serves double duty — WATI needs a URL, owners need a place to find you
- Phase C third: now you have something worth deploying
- Phase D next up: Meta verification is approved, no external dependency left — implement whenever convenient
- **Phase F before onboarding any second real paying owner** — today all fee money settles into your own Razorpay account regardless of institute; this is higher priority than Phase E even though it's lettered after it. Direction is now decided (BYO keys), so this is unblocked and just needs building.
- Phase E ongoing: polish after real users give feedback

---

## PHASE A — Fix Ship-Blockers 🟡 PARTIAL (A.3 pending manual test)

---

### Task A.1 — Fix nginx.conf to proxy all API route prefixes

**Why this is critical:** In the Docker prod stack, the React app is served by nginx. nginx proxies API calls to the FastAPI backend. The current config only proxies `/student/*` and `/owner/*`. Every owner dashboard action (create batch, mark fee, take attendance) hits `/batch/*`, `/fee/*`, `/attendance/*`, `/enrollment/*`, `/scores/*` — all of which nginx currently serves as 404s. The entire owner dashboard breaks in production.

- [x] Update `batchbookui/nginx.conf` — extend the proxy location regex to cover all backend prefixes:
  ```nginx
  location ~ ^/(student|owner|batch|fee|attendance|enrollment|scores|parent|teacher|docs|redoc|openapi\.json)(/.*)?$ {
  ```
- [ ] Verify: `make prod` → open `http://localhost` → owner login → create a batch → confirm no 404s in browser network tab

**Verified by:** _(pending manual smoke test with `make prod`)_

---

### Task A.2 — Wire OwnerDashboard header stats

**Why:** The dashboard header currently shows no live data. An owner opening their app for the first time sees a blank header instead of "12 students enrolled | ₹8,400 collected | 87% avg attendance" — the numbers that prove the product is working.

**Backend is already done** — `GET /owner/stats` exists and returns `{ total_students, fee_collected_this_month, avg_attendance_pct }`.

- [x] In `OwnerDashboard.jsx`: add a `useEffect` on mount that calls `GET /owner/stats` via `ownerService.js`
- [x] Add `getOwnerStats()` to `ownerService.js` if not already there
- [x] Render the 3 stats in the dashboard header bar
- [x] Handle loading state (show `—` while fetching) and error state (silently hide the bar)

**Verified by:** _(code already implemented — pending manual smoke test)_

---

### Task A.3 — Manual end-to-end verification of Phase 0 flows

**Why:** Three critical flows have code written but were never tested against a running app. They could be broken in subtle ways (wrong endpoint, wrong localStorage key, redirect loops).

Run the following test scripts against `make dev` (local Docker):

- [x] **Owner new-user flow:** Fresh phone number → `/onboarding` → select Owner → OTP → verify OTP → should land at `/owner/setup` (not `/owner/dashboard`). Complete setup → should land at `/owner/dashboard`.
- [x] **Owner returning-user flow:** Known owner phone → OTP → should skip setup and go straight to `/owner/dashboard`.
- [x] **Student/parent flow:** Parent phone → `/onboarding` → select Student → fill parent details → OTP → should land at `/dashboard/student` with real data (not error screen).
- [x] **Role guard test:** Log in as owner → try navigating to `/dashboard/student` by URL → should redirect to `/phone-login`. Log in as parent → try `/owner/dashboard` → should redirect to `/onboarding`.
- [x] **Sign out:** Click sign out → localStorage `bb_role` and `bb_student_id` should be cleared → protected routes should redirect.

For each flow, write what you saw under "Verified by" in this file.

**Verified by:** _(bedant sharma)_
### Owner new user flow

---
on the /onboarding page there is no option to get started as a owner there is only an teacher path and a student path 

there is a page that is /phone-login that is for owner onboarding but
i think that it should be mapped to the onboarding flow itself.

rest of the flow works fine. the setup -> dashboard flow works


### Returning owner flow 

---

works as expected just a small thing in the /otp-verification page if i 
enter a wrong otp once and then resend otp then try to fill that otp i was not able to do that 
please look into that if you have time 

### Student onboarding flow 

---

works as expected. 

### role guardrails 

---

when login as student i tried to visit the /owner/dashboard endpoint and got redirected to /phone-login screen

### Sign out button

---
works fine for the student page

as it works for the student page i also expect it to work for the parent page

---

### Task A.4 — Surface Razorpay payment link in student dashboard

**Why:** Razorpay backend is done. But parents who see "Fee Due" in the student dashboard have no button to pay. The core value prop — one-click fee payment — is invisible.

- [x] In `dashboardService.js`, add `getFeeStatus()` (already exists — check it returns `{ payment_link }` field)
- [x] In `StudentDashboard.jsx` Overview tab: if `feeDue === true`, show a "Pay Now" button that opens `payment_link` in a new tab
- [x] If `payment_link` is null (owner hasn't generated it yet), show "Contact your institute" instead of a broken button

**Verified by:** _(pending manual smoke test)_

---

### Task A.5 — Wire student Batches, Schedule, and Fees tabs

**Why:** The student sidebar shows 4 tabs (Overview, Batches, Schedule, Fees) but 3 of them are `cursor: not-allowed` stubs. A parent who taps "Schedule" and sees nothing will think the app is broken.

- [x] Create `BatchesTab` inside `StudentDashboard.jsx` — lists batch names, subjects, and monthly attendance %
- [x] Create `ScheduleTab` — displays today's classes + upcoming events grouped by day
- [x] Create `FeesTab` — shows current month status per batch, "Pay Now" button if `payment_link` present
- [x] In `StudentDashboard.jsx`: replaced `cursor: not-allowed` stubs with real content components; `activeTab` state drives rendering

**Verified by:** _(pending manual smoke test)_

---

## PHASE B — Real Landing Page  ✅Done

**Why this comes before deployment:** Two reasons:
1. WATI (WhatsApp Business API) requires a business website URL during Meta verification. The current placeholder card at `/` doesn't count — Meta looks for a real page with product description, privacy policy, and contact info.
2. When an owner hears about BatchBook (word of mouth, Google search), they need to land somewhere that convinces them to sign up.

---

### Task B.1 — Build a real marketing landing page

**Replace** `src/components/LandingPage.jsx` with a proper page. It does not need to be fancy — it needs to communicate clearly.

Required sections:

- [x] **Hero:** headline + "Get Started Free" CTA → `/onboarding`
- [x] **3 feature cards:** Fee Management, Attendance, Test Scores
- [x] **How it works:** 3 numbered steps + second CTA
- [x] **Social proof placeholder:** "Join 50+ coaching institutes"
- [x] **Footer:** BatchBook © 2026 · Privacy Policy link · contact email
- [x] **Privacy Policy page** at `/privacy-policy` — covers data collection, usage, retention, contact
- [x] **Add `/privacy-policy` route in `App.jsx`**
- [x] **Fix Vercel SPA routing** — `vercel.json` rewrite rule so direct URL hits don't 404

**Verified by:** _(deployed at batchbookui.vercel.app — pending visual check)_

---

### Task B.2 — Deploy landing page to get a real URL

**Why:** Before the full Docker deployment, get `yourdomain.com` serving the landing page so you can submit the URL to WATI immediately.

Recommended approach: **Vercel** (free, instant, auto-deploys from git push, gives HTTPS)

- [x] Push `batchbookui` frontend to its own GitHub repo
- [x] Sign up at vercel.com → import `batchbookui` repo → set env vars → deployed
- [x] Vercel URL: **https://batchbookui.vercel.app** — submit this to WATI as business URL
- [ ] Later (Task C.3), point your custom domain here and update the WATI registration

**Verified by:** _(live at batchbookui.vercel.app — /privacy-policy confirmed working after vercel.json fix)_

---

## PHASE C — Production Deployment 🟡 PARTIAL (C.5 pending)

**Decision to make first:** Where to host the backend?

| Option | Cost | Pros | Cons |
|--------|------|------|------|
| **Render.com** | Free (spins down) / $7/mo (always-on) | Dead simple Docker deploy, no ops | Free tier sleeps after 15 min inactivity |
| **Railway.app** | ~$5/mo | Good DX, fast deploys | Less mature |
| **Fly.io** | ~$3–5/mo | Fastest cold starts | CLI-heavy setup |
| **DigitalOcean Droplet** | $6/mo | Full control, persistent | You manage the server |

**Recommendation:** Start with **Render.com** (the $7/month "Starter" plan — no sleep). The database is already on Supabase so no DB cost. Frontend goes on **Vercel** (already set up in B.2). Total cost: ~$7/month.

---

### Task C.1 — Buy a domain ✅ DONE

- [x] Buy a `.com` or `.in` domain — suggestions: `batchbook.in`, `batchbook.app`, `trybatchbook.com`
- [x] Recommended registrar: Namecheap or Google Domains
- [x] Note the domain here once purchased: **Domain: batchbook.in (Namecheap)**

---

### Task C.2 — Set up Render.com for the backend ✅ DONE

- [x] Sign up at render.com
- [x] "New Web Service" → connect `github.com/bedantsharma/BatchBook`
- [x] Environment: Docker
- [x] Dockerfile path: `./Dockerfile`
- [x] Docker build target: `prod`
- [x] Set all env vars in Render dashboard:
  - `DATABASE_URL`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `RAZORPAY_KEY_ID`
  - `RAZORPAY_KEY_SECRET`
  - `PROJECT_NAME=BatchBook`
  - `PORT=8000`
- [x] First deploy: service is live on the default `*.onrender.com` URL
- [x] Verify `https://batchbook-g9c0.onrender.com/docs` loads — confirmed, Swagger UI renders ("Batch Book - Swagger UI")
- [x] Migrations — same Supabase DB as dev, already at head; no manual `alembic upgrade head` needed
- [x] Custom domain `api.batchbook.in` added in Render, DNS CNAME added in Namecheap, domain verified (had to clear Namecheap's default parking CNAME/URL-redirect records and a conflicting CAA record first — Let's Encrypt cert issuance needs a clean CAA or one that allows `letsencrypt.org`)

**Verified by:** _(bedant sharma — live at api.batchbook.in, /docs confirmed loading)_

---

### Task C.3 — Configure frontend for production ✅ DONE

- [x] Add custom domain in Vercel: `batchbook.in` (naked domain) + `www.batchbook.in`
- [x] Update CORS in `app.py` — added `https://batchbookui.vercel.app`, `https://batchbook.in`, `https://www.batchbook.in` to `allow_origins` (done before first Render deploy, to avoid a redeploy just for CORS)
- [x] In Vercel project settings, add env var: `VITE_API_BASE_URL=https://api.batchbook.in`
- [x] Fixed a bug along the way: `batchbookui/.env.production` (committed to git) had a leftover placeholder `VITE_API_BASE_URL=https://your-backend-url.com`, and the Vercel dashboard var had initially been misnamed `VITE_API_URL` — neither matched what `src/services/api.js` actually reads (`VITE_API_BASE_URL`), so OTP requests were silently calling the wrong host. Fixed in both places (PR [#25](https://github.com/bedantsharma/batchbookui/pull/25), merged) and redeployed.

**Verified by:** _(bedant sharma — confirmed OTP requests hit api.batchbook.in after the fix)_

---

### Task C.4 — Set up CI/CD with GitHub Actions ✅ DONE

**Why:** Without CI, a bad push goes straight to prod. With CI, tests run first and the deploy only happens if tests pass.

- [x] Created `.github/workflows/deploy-backend.yml` — a `test` job (`uv run pytest -q`) runs on every push *and* every PR into `master`; a `deploy` job runs only on a direct push to `master`, only after `test` passes, and curls the Render deploy hook
- [x] `RENDER_DEPLOY_HOOK` GitHub secret added (from Render dashboard → service → Settings → Deploy Hook)
- [x] For frontend: Vercel already auto-deploys on every push to `batchbookui` — no extra config needed

**Verified by:** _(bedant sharma — pushed to master 2026-06-23, confirmed via `gh run watch`: `test` passed in 22s, `deploy` job fired the Render hook successfully — run [28049802701](https://github.com/bedantsharma/BatchBook/actions/runs/28049802701))_

---

### Task C.5 — Smoke test the full production stack

- [ ] Owner flow end-to-end on `https://yourdomain.com` (phone login → setup → batches → fees → attendance)
- [ ] Student flow: parent OTP → student dashboard → see real data
- [ ] Open browser DevTools → Network tab → confirm zero 404s on API calls
- [ ] Test on a real phone (not just desktop Chrome) — these users are on Android phones

**Verified by:** _(pending)_

---

## PHASE D — WhatsApp Notifications via Meta Cloud API 🟢 READY (verification approved 2026-06-21)

> Going direct to Meta's Cloud API instead of WATI — see "Decision" note in Current Reality above. No BSP, no monthly fee, same integration shape originally planned for WATI.

---

### Task D.0 — One-time Meta-side setup (do first, no code)

- [x] In Meta Business Suite → Business Settings → System Users: create/use a System User, generate a **permanent access token** (scopes `whatsapp_business_messaging`, `whatsapp_business_management`, expiry: Never) — the default testing-page token expires in ~1-2h and will break prod notifications silently if used by mistake
- [x] In WhatsApp Manager: note the `phone_number_id` and `WABA ID` for the verified number
- [x] Confirm current messaging tier (new WABAs start at 250 unique recipients/24h) — fine at current scale, just be aware before any bulk "remind-all" send

---

### Task D.1 — WhatsApp client + notification service

- [x] Add to `.env`: `META_WHATSAPP_TOKEN=xxxxxxxx`, `META_WHATSAPP_PHONE_NUMBER_ID=xxxxxxxx`
- [x] Add to `config.py` Settings class: `meta_whatsapp_token: str` and `meta_whatsapp_phone_number_id: str` (replaces the unused `wati_api_endpoint` / `wati_api_token` fields)
- [x] Create `BatchBook/clients/whatsapp_client.py` — async HTTP client using `httpx`; one method `send_template_message(phone, template_name, params, language="en")` that POSTs to `https://graph.facebook.com/v23.0/{phone_number_id}/messages`
- [x] Update `BatchBook/services/notification_service.py` — replace the WATI-stub log lines with real calls into `whatsapp_client`; keep the same four function signatures (`send_enrollment_invite`, `send_fee_reminder`, `send_fee_receipt`, `send_absence_alert`)

---

### Task D.2 — Fee reminder and receipt (Tasks 3.4)

**Templates to create in WhatsApp Manager** (category: Utility → wait for approval, usually minutes–24h):
- `fee_reminder`: "Hi {{1}}, your fee of ₹{{2}} for {{3}} is due on {{4}}." + URL button → Razorpay payment link (pass the link as the button's dynamic URL param, don't embed it in body text)
- `fee_receipt`: "Hi {{1}}, payment of ₹{{2}} received for {{3}} on {{4}}. Thank you!"

- [x] Add to `fee_route.py`: `POST /fee/remind/{record_id}` and `POST /fee/remind-all`
- [x] Auto-send `fee_receipt` template after `mark_payment()` succeeds in `fee_service.py`
- [x] Wire the "Remind" button in `FeesPage.jsx` to call `POST /fee/remind/{record_id}` (batchbookui PR #26)

---

### Task D.3 — Absence alert (Task 4.2)

**Template to create in WhatsApp Manager** (category: Utility):
- `absence_alert`: "Hi, {{1}} was absent from {{2}} today ({{3}}). Please contact us if this is unexpected."

- [x] Add `send_absence_alert(enrollment_id, date)` to `notification_service.py`
- [x] In `attendance_service.py` `bulk_mark()`: after writing ABSENT rows, fire `send_absence_alert` as a background task (use FastAPI `BackgroundTasks`) for each newly-absent enrollment
- [x] Don't block the HTTP response on the WhatsApp call — use `BackgroundTasks` so the attendance mark is instant

---

## PHASE F — Multi-Tenant Payment Settlement (Bring-Your-Own Razorpay Account) 🟢 READY (decision finalized 2026-06-23)

**Why this phase exists:** `clients/razorpay_client.py` builds one global `razorpay.Client` from your personal `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`, and `fee_service.py: generate_payment_link()` uses that same client for every institute's fee records. **Every parent payment, for every owner, currently settles into your own Razorpay account, not the owner's.** Fine for a single pilot institute (yours); breaks the moment a second real owner signs up — you'd be holding other people's tuition money and manually forwarding it, which is an operational headache and a real regulatory question under RBI's Payment Aggregator (PA-PG) rules.

There is also no webhook handler today — `PATCH /fee/record/{id}/pay` requires an owner to manually mark a record paid after checking Razorpay's dashboard themselves. Nothing confirms a payment server-side.

### Decision: each owner brings their own Razorpay account (decided 2026-06-23, supersedes the 2026-06-21 Route decision)

Route + Linked Accounts (the original plan) was abandoned after two findings: (1) a Razorpay support-chatbot claim about a ₹40L turnover eligibility threshold turned out to be unverifiable and likely a conflation with an unrelated GST rule; (2) reading Razorpay's actual Linked Accounts docs showed there is **no hosted KYC redirect** for Route — BatchBook itself would have had to collect each owner's bank details, contradicting the entire premise of "BatchBook never touches sensitive data." On top of that, RBI's Sept 15, 2025 Master Direction on Payment Aggregators states a PA business "shall not carry out marketplace business" and requires marketplaces to ensure sellers are separately, fully onboarded — tightening exactly the kind of money-aggregation Route relies on.

**Chosen model:** owner signs up for their own Razorpay merchant account directly at razorpay.com (Individual or Proprietorship business type — Udyam registration is the realistic business-proof document for a solo coaching institute), completes KYC independently, and pastes their own API Key ID/Secret into a new BatchBook Settings page. BatchBook never custodies or routes anyone else's money — each institute's payments go straight to that institute's own Razorpay account. This was the option rejected in the original comparison table for onboarding friction; it's back because it's the only model where BatchBook doesn't aggregate funds across unrelated merchants, keeping it outside PA-PG scope (the same pattern used by SaaS platforms that let a customer "bring their own payment gateway").

Open questions from the decision doc are now resolved:
- **Platform fee model:** flat subscription instead of a per-transaction cut (Route's auto-split is gone since money never touches a BatchBook-controlled account) — ₹700/month up to 50 students, ₹15/student above that headcount.
- **Website requirement:** confirmed via Razorpay's own FAQ — no website is required to generate live API keys or use Payment Links.
- **PA-PG scope:** confirmed by analogy to an existing BYO-keys model the user has direct experience with at their day job — same pattern, same conclusion (outside PA-PG scope).
- **Onboarding UX:** KYC is fully offloaded to Razorpay's own (reportedly painless) onboarding flow; BatchBook's job is just a guided Settings page explaining what the owner is about to do, not replicating any part of KYC itself.

### Step-by-step: how this fits into the existing flow

1. **Signup/setup is unchanged.** Owner still does OTP → `/owner/setup` (institute name + city only — `OwnerSetup.jsx` → `POST /owner/institute`) → lands at `/owner/dashboard`, exactly as today.
2. **A new Settings page is added to the dashboard** (doesn't exist yet — `OwnerDashboard.jsx`'s sidebar currently only has Students / Batches / Fees / Attendance / Tests). It has a "Payouts" section: a guided explainer ("you'll need your own Razorpay account to collect fees online — here's what that involves") plus two input fields for Key ID and Key Secret, and a connection status (`Not connected` / `Connected` / `Needs reconnect`).
3. **The trigger is lazy, not forced.** The first time an owner clicks "Generate Payment Link" on a fee record without connected keys, a banner appears — "Connect your Razorpay account to start collecting fees online" — linking to Settings → Payouts. Cash-only institutes never see this at all.
4. **Owner signs up at razorpay.com independently**, completes their own KYC (Individual/Proprietorship + Udyam), and generates a Key ID + Secret from their own Dashboard → Account & Settings → API Keys.
5. **Owner pastes Key ID + Secret into BatchBook's Settings page.** Backend validates the key prefix (`rzp_live_`, reject/warn on `rzp_test_`), runs a cheap test call (e.g. fetch account details) to confirm the keys actually work, then encrypts the secret at rest and stores both on the `Institute` row. Status becomes `Connected`.
6. **Every `generate_payment_link()` call for that institute** instantiates a `razorpay.Client(key_id, key_secret)` scoped to that institute instead of the global client — no `transfers` array, no split logic, because the money was never BatchBook's to route in the first place.
7. **Parent pays the link** → money lands directly in the owner's own Razorpay account → settles to their own bank account on their own account's normal cycle. BatchBook never holds or moves the money at any point.
8. **If the owner rotates/revokes keys on their own dashboard**, the next payment-link call fails with an auth error. BatchBook catches this, flips status to `Needs reconnect`, and shows a clear reconnect prompt in Settings rather than failing silently.

---

### Task F.1 — Add Razorpay credential fields to `Institute` and a Settings page

- [ ] Add nullable `razorpay_key_id` (plain) and `razorpay_key_secret` (**encrypted at rest**) columns to `InstituteSchema` — migrate with Alembic
- [ ] Add `Settings` to the dashboard `NAV_ITEMS` sidebar and a corresponding route
- [ ] Build the "Payouts" section: guided explainer of what connecting Razorpay involves, Key ID/Secret input fields, connection status (`Not connected` / `Connected` / `Needs reconnect`)
- [ ] On the Fees page, show a "Connect Payouts" banner the first time an owner without connected keys tries to generate a payment link

**Verified by:** _(pending)_

---

### Task F.2 — Validate and store owner-provided keys

- [ ] On Settings save: reject keys with an `rzp_test_` prefix (or warn clearly that test-mode payments won't actually settle anywhere real)
- [ ] Run a lightweight Razorpay API call (e.g. fetch account/contact) with the submitted keys before saving, to confirm they're valid and live — surface a clear error if the call fails
- [ ] Encrypt `razorpay_key_secret` at rest; never log or return it in any API response after initial save (Settings GET should return only a masked indicator, not the secret itself)

**Verified by:** _(pending)_

---

### Task F.3 — Per-institute Razorpay client in `fee_service.py`

- [ ] Replace the global `clients/razorpay_client.py` usage in `generate_payment_link()` with a per-request `razorpay.Client(institute.razorpay_key_id, decrypted_secret)` scoped to the institute owning the fee record
- [ ] Reject `generate_payment_link()` calls for institutes with no connected keys (clear error pointing to Settings)
- [ ] Remove the now-dead split/transfer logic path entirely — there is none in this model

**Verified by:** _(pending)_

---

### Task F.4 — Per-institute Razorpay payment webhook handling

**Why:** Payment confirmation is currently 100% manual. A webhook makes the fee status update itself the moment Razorpay confirms payment, and unblocks the auto fee-receipt WhatsApp send already planned in Task D.2. Each owner's Razorpay account has its own webhook secret, so the single global `RAZORPAY_WEBHOOK_SECRET` assumption from the old Route plan no longer holds.

- [ ] Add nullable `razorpay_webhook_secret` (encrypted) column to `InstituteSchema`; owner registers BatchBook's webhook URL in their own Razorpay dashboard and pastes the secret back into Settings
- [ ] Add `POST /webhooks/razorpay/{institute_id}` route (no JWT auth — verified by signature instead), keyed per institute so the right stored secret is used for verification
- [ ] Verify the `X-Razorpay-Signature` header against the raw request body using `razorpay_client.utility.verify_webhook_signature()` and that institute's stored secret
- [ ] Handle the `payment_link.paid` event: look up the `FeeRecord` by its stored `payment_link`/reference, then call the existing `fee_service.mark_payment()` logic automatically with the captured amount and Razorpay `payment.id` as the reference
- [ ] Keep `PATCH /fee/record/{id}/pay` as-is for manual/offline (cash) payments — don't remove it

**Verified by:** _(pending)_

---

### Task F.5 — Key rotation/revocation detection

- [ ] On any `generate_payment_link()` auth failure against an institute's stored keys, flip `Institute` payout status to `Needs reconnect` and surface that state clearly in Settings
- [ ] Add a manual "Test connection" button in Settings that re-validates the stored keys on demand (reuses the Task F.2 validation call)

**Verified by:** _(pending)_

---

### Task F.6 — Subscription billing for the platform fee

**Why:** Route's automatic 97/3 split is gone — BatchBook needs its own billing mechanism now that it never touches owner payment flows. Pricing decided: ₹700/month up to 50 students, ₹15/student above that headcount.

- [ ] Decide and implement how BatchBook charges institutes for its own subscription (separate Razorpay subscription/invoice on BatchBook's own account, billed to the owner directly — not a transaction split)
- [ ] Track per-institute student headcount to compute the tier/overage at billing time

**Verified by:** _(pending)_

---

### Task F.7 — End-to-end test before onboarding a second real owner

- [ ] In Razorpay test mode (on a real Razorpay test account, not BatchBook's): paste test keys into Settings, generate a payment link, pay it with a test card/UPI, confirm the webhook fires and `FeeRecord` updates automatically
- [ ] Confirm the reconnect flow: revoke the test keys on the Razorpay dashboard, confirm the next payment-link call flips status to `Needs reconnect`, reconnect with fresh keys, confirm it recovers
- [ ] Only after this passes: onboard the first real second owner

**Verified by:** _(pending)_

---

## PHASE E — Polish & Completeness ⬜ NOT-STARTED

Do these after real users start using the app and give feedback. Don't do them before deployment.

---

### Task E.1 — Multi-child parent: child selector

**Why:** A parent with 2 children enrolled at the same institute currently sees only the first child's data. The `bb_student_id` in localStorage is whichever child came first in the API response.

- [ ] In `dashboardService.js` `getStudentProfile()`: if `parent.children.length > 1`, don't auto-select — return all children
- [ ] In `StudentDashboard.jsx`: if multiple children, show a child-selector dropdown at the top of the sidebar (name chips or a select menu)
- [ ] Selecting a child sets `bb_student_id` in localStorage and triggers a data reload

---

### Task E.2 — Attendance streak computation

**Why:** Streak is currently hardcoded to 0 in `dashboardService.js`. It's shown on the student Overview as a card.

- [ ] Add a `GET /student/me/streak?student_id=X` backend endpoint in `student_dashboard_route.py`
- [ ] Logic: count consecutive days with at least one PRESENT record, working backwards from today; stop at the first ABSENT or gap day
- [ ] Wire it in `dashboardService.js` `getAttendance()`: add the streak call to the concurrent `Promise.all`

---

### Task E.3 — Fee receipt PDF download

**Why:** Owners sometimes need to give a paper receipt. A "Download Receipt" button is a frequently requested feature for coaching institutes.

- [ ] Add `GET /fee/record/{record_id}/receipt` endpoint — returns a simple PDF (use `reportlab` or `fpdf2`)
- [ ] PDF content: institute name, student name, batch, month, amount paid, date, "Receipt No. {record_id}"
- [ ] Wire a "Download" icon button in `FeesPage.jsx` for FULLY_PAID records

---

### Task E.4 — Run E2E tests in CI

**Why:** 5 Playwright spec files exist but have never been run. They likely need fixes after all the real wiring done in Phase 0.

- [ ] Run `npx playwright test` locally against `make dev` — see what passes and what fails
- [ ] Fix failing specs (likely auth flows and data-dependent tests)
- [ ] Add a second GitHub Actions job that spins up `make dev-d`, waits for health, runs Playwright, then tears down

---

## ⚠️ Your Actions Required Right Now

| Action | Unblocks |
|--------|---------|
| Fix the 3 bugs found during A.3 manual testing (owner path missing from `/onboarding`, OTP resend bug, parent sign-out) | Confidence before real users |
| Full smoke test on `https://batchbook.in` (Task C.5) | Confidence before real users |
| Wait for Meta Business verification approval | WATI credentials (Phase D) |
| Build the BYO-Razorpay Settings page + per-institute client (Tasks F.1–F.7) | Safe onboarding of any real second paying owner |

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

## How to Run Right Now

```bash
# Backend (Docker dev):
make dev

# Backend (no Docker):
uv run uvicorn app:app --reload --port 8000

# Frontend:
cd batchbookui && npm run dev

# Tests:
uv run pytest -v   # 278 tests

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
