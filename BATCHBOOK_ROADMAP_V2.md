# BatchBook — Roadmap v2 (June 2026 → Deployment)

> **How to use this file:** Read "Current Reality" first. Then pick the first unchecked item under the current phase. Phases A and B must complete before Phase C (deployment). Phase D unlocks only after WATI credentials arrive.

---

## Current Reality (as of June 2026)

### What actually works end-to-end
- **247 backend tests passing** — models, routes, services all solid
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
- WATI tasks (3.4, 4.2) — Meta/WhatsApp Business verification **applied for** (using `batchbook.in`, live since Task C.3). Awaiting Meta's approval before WATI API credentials are issued — implement Phase D the moment they arrive.

---

## Gap Summary Table

| Gap | Severity | Blocks |
|-----|----------|--------|
| All institutes' fee payments settle into the platform's own Razorpay account, not the owner's — single global `razorpay.Client` in `clients/razorpay_client.py` | 🔴 CRITICAL | Onboarding any real second paying owner; regulatory exposure (RBI Payment Aggregator rules) |
| No Razorpay webhook handler — payment status is 100% manual via `PATCH /fee/record/{id}/pay` | 🔴 CRITICAL | Reliable fee status, auto `fee_receipt` WATI send (Task D.2) |
| Meta/WhatsApp Business verification pending approval | 🟡 HIGH | WATI credentials (Phase D) |
| No CI/CD pipeline | 🟡 HIGH | Safe deployments |
| Owner header stats not wired | 🟡 HIGH | UX completeness |
| Student Batches/Schedule/Fees tabs greyed out | 🟡 HIGH | Student app completeness |
| Student Razorpay payment link not surfaced | 🟡 HIGH | Core value prop for parents |
| Full prod stack never smoke-tested end-to-end on `batchbook.in` | 🟡 HIGH | Confidence before real users |
| Attendance streak always 0 | 🟠 MEDIUM | Student UX |
| Multi-child parent has no child selector | 🟠 MEDIUM | Parents with >1 child |
| E2E tests never run in CI | 🟠 MEDIUM | Regression safety |
| No `@batchbook.in` email (no MX records) | 🟢 LOW | Branded contact email only |
| No PDF fee receipt | 🟢 LOW | Nice-to-have |

---

## Roadmap Overview

| Phase | Goal | Status |
|-------|------|--------|
| **A** | Fix ship-blockers — nginx, stats, student tabs | 🟡 PARTIAL — A.1 ✅ A.2 ✅ A.4 ✅ A.5 ✅ · A.3 pending manual test |
| **B** | Landing page (real marketing page + WATI website URL) | ✅ DONE — deployed at batchbookui.vercel.app |
| **C** | Deployment — hosting, domain, SSL, CI/CD | 🟡 PARTIAL — C.1 ✅ C.2 ✅ C.3 ✅ · C.4 (CI/CD) and C.5 (smoke test) remaining |
| **D** | WATI notifications (fee reminders, absence alerts) | 🚫 BLOCKED — Meta Business verification applied for, awaiting approval |
| **F** | Multi-tenant payments — Razorpay Route + Linked Accounts (hosted onboarding) + webhooks | 🚫 BLOCKED — needs Razorpay Route eligibility confirmed (Task F.1) |
| **E** | Polish — multi-child, streak, receipts, E2E CI | ⬜ NOT-STARTED |

**Sequencing rationale:**
- Phase A first: fix what's broken before putting it in front of anyone
- Phase B second: landing page serves double duty — WATI needs a URL, owners need a place to find you
- Phase C third: now you have something worth deploying
- Phase D whenever: WATI credentials may arrive any time; implement immediately when they do
- **Phase F before onboarding any second real paying owner** — today all fee money settles into your own Razorpay account regardless of institute; this is higher priority than Phase E even though it's lettered after it
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

## PHASE C — Production Deployment ⬜ NOT-STARTED

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

### Task C.4 — Set up CI/CD with GitHub Actions

**Why:** Without CI, a bad push goes straight to prod. With CI, tests run first and the deploy only happens if 247 tests pass.

- [ ] Create `.github/workflows/deploy-backend.yml`:
  ```yaml
  name: Deploy Backend
  on:
    push:
      branches: [master]
  jobs:
    test-and-deploy:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: astral-sh/setup-uv@v3
        - run: uv run pytest -q
        - name: Deploy to Render
          run: curl "${{ secrets.RENDER_DEPLOY_HOOK }}"
  ```
- [ ] In Render dashboard → your service → "Deploy hooks" → copy the URL → add as `RENDER_DEPLOY_HOOK` GitHub secret
- [ ] For frontend: Vercel already auto-deploys on every push to `batchbookui` — no extra config needed

**Verified by:** _(pending — push a dummy commit to master and verify Actions runs tests then triggers Render deploy)_

---

### Task C.5 — Smoke test the full production stack

- [ ] Owner flow end-to-end on `https://yourdomain.com` (phone login → setup → batches → fees → attendance)
- [ ] Student flow: parent OTP → student dashboard → see real data
- [ ] Open browser DevTools → Network tab → confirm zero 404s on API calls
- [ ] Test on a real phone (not just desktop Chrome) — these users are on Android phones

**Verified by:** _(pending)_

---

## PHASE D — WATI Notifications 🚫 BLOCKED (Meta verification pending)

> Meta/WhatsApp Business verification has been **submitted** using `batchbook.in` as the business website. Implement these the moment your WATI account is approved and you have the API endpoint + token.

---

### Task D.1 — WATI client + notification service

- [ ] Add to `.env`: `WATI_API_ENDPOINT=https://live-mt-server.wati.io/XXXXX` and `WATI_API_TOKEN=xxxxxxxx`
- [ ] Add to `config.py` Settings class: `wati_api_endpoint: str` and `wati_api_token: str`
- [ ] Create `BatchBook/clients/wati_client.py` — async HTTP client using `httpx`; one method `send_template_message(phone, template_name, params)`
- [ ] Create `BatchBook/services/notification_service.py` — wraps WATI client; three functions: `send_fee_reminder()`, `send_fee_receipt()`, `send_absence_alert()`

---

### Task D.2 — Fee reminder and receipt (Tasks 3.4)

**WATI templates to create** (create in WATI dashboard → wait 24–48h for WhatsApp approval):
- `fee_reminder`: "Hi {{1}}, your fee of ₹{{2}} for {{3}} is due on {{4}}. Pay here: {{5}}"
- `fee_receipt`: "Hi {{1}}, payment of ₹{{2}} received for {{3}} on {{4}}. Thank you!"

- [ ] Add to `fee_route.py`: `POST /fee/remind/{record_id}` and `POST /fee/remind-all`
- [ ] Auto-send `fee_receipt` template after `mark_payment()` succeeds in `fee_service.py`
- [ ] Wire the "Remind" button in `FeesPage.jsx` to call `POST /fee/remind/{record_id}`

---

### Task D.3 — Absence alert (Task 4.2)

**WATI template to create:**
- `absence_alert`: "Hi, {{1}} was absent from {{2}} today ({{3}}). Please contact us if this is unexpected."

- [ ] Add `send_absence_alert(enrollment_id, date)` to `notification_service.py`
- [ ] In `attendance_service.py` `bulk_mark()`: after writing ABSENT rows, fire `send_absence_alert` as a background task (use FastAPI `BackgroundTasks`) for each newly-absent enrollment
- [ ] Don't block the HTTP response on WATI — use `BackgroundTasks` so the attendance mark is instant

---

## PHASE F — Multi-Tenant Payment Settlement (Razorpay Route + Linked Accounts) 🚫 BLOCKED (needs Task F.1)

**Why this phase exists:** `clients/razorpay_client.py` builds one global `razorpay.Client` from your personal `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`, and `fee_service.py: generate_payment_link()` uses that same client for every institute's fee records. **Every parent payment, for every owner, currently settles into your own Razorpay account, not the owner's.** Fine for a single pilot institute (yours); breaks the moment a second real owner signs up — you'd be holding other people's tuition money and manually forwarding it, which is an operational headache and a real regulatory question under RBI's Payment Aggregator (PA-PG) rules.

There is also no webhook handler today — `PATCH /fee/record/{id}/pay` requires an owner to manually mark a record paid after checking Razorpay's dashboard themselves. Nothing confirms a payment server-side.

### Decision: Razorpay Route + Linked Accounts, hosted onboarding (decided 2026-06-21)

Three options were weighed:

| Option | What the owner ends up with | Verdict |
|---|---|---|
| Bring-your-own Razorpay account | Owner independently signs up for their own Razorpay merchant account outside BatchBook, pastes their own API Key ID/Secret into Settings | ❌ Rejected — too much onboarding friction for a solo coaching-institute owner; defeats the point of replacing WhatsApp/paper registers |
| Aggregator/Partner OAuth onboarding | Owner gets a fully independent Razorpay merchant account via a redirect flow you host; you get an OAuth access token scoped to their account, no split needed since the money is theirs from the moment it's captured | 🕗 Deferred — requires Razorpay to approve you as a registered Aggregator Partner, a heavier program than plain Route access; revisit only if being "merchant of record" for every institute becomes a real legal concern at scale |
| **Route + Linked Accounts, hosted onboarding** | Owner is redirected to a Razorpay-hosted KYC page, comes back with just an `account_id` (e.g. `acc_GLGeLkU2JUeyDZ`) — **not** API keys. The Linked Account lives under *your* master Razorpay account; every API call (payment-link creation, the split) still uses *your* `RAZORPAY_KEY_ID`/`SECRET` | ✅ **Chosen** |

**The clarification that drove this decision:** the assumption that "the owner needs their own API creds to get rid of our settlement headache" doesn't hold. Under Route, Razorpay's own nodal account custodies every payment and auto-splits + auto-settles it on its normal cycle (~T+3) directly to each party's bank account — that happens regardless of whether the owner holds any credentials. Credential ownership and settlement-headache-removal are two separate axes; Route already gives us the second without needing the first.

### Step-by-step: how this fits into the existing flow

1. **Signup/setup is unchanged.** Owner still does OTP → `/owner/setup` (institute name + city only — `OwnerSetup.jsx` → `POST /owner/institute`) → lands at `/owner/dashboard`, exactly as today. No KYC fields get added here — doing so would block an owner from even seeing the dashboard before they've decided whether they want online fee collection at all.
2. **A new Settings page is added to the dashboard** (doesn't exist yet — `OwnerDashboard.jsx`'s sidebar currently only has Students / Batches / Fees / Attendance / Tests). It has one new "Payouts" section showing connection status: `Not connected` / `Pending verification` / `Active`.
3. **The trigger is lazy, not forced.** The first time an owner clicks "Generate Payment Link" on a fee record without a connected payout account, a banner appears — "Connect your bank account to start collecting fees online" — linking to Settings → Payouts. Cash-only institutes that never touch online collection never see this at all.
4. **Owner clicks "Connect Payouts"** → backend calls Razorpay `POST /accounts` to create a shell Linked Account (just enough to get an `account_id`), then redirects the owner to Razorpay's hosted onboarding page for that `account_id`. Razorpay itself collects the KYC there (legal name, PAN, bank account + IFSC, supporting documents) — **BatchBook never touches or stores this sensitive data**.
5. **Owner finishes KYC on Razorpay's page → gets redirected back** to a BatchBook callback URL carrying the `account_id` (plus an auth code, per Razorpay's redirect flow) — not API keys. Backend stores `razorpay_linked_account_id` on the `Institute` row with status `pending_kyc`.
   - **If the owner abandons partway** (closes the tab, hits back, or returns without ever submitting KYC to Razorpay) — there's no webhook for this, since `account.activated` only fires on success. The shell Linked Account already exists in status `kyc_incomplete`. Don't treat this as an error: the institute simply stays gated from "Generate Payment Link" (the existing safe default), and Settings shows "Setup incomplete" with a **"Continue Setup"** button that re-redirects to the hosted onboarding page for the *same* `account_id` — never create a second Linked Account for one institute.
   - Because there's no reliable "they bailed" signal, reconcile on every Settings page load (and via a manual "Refresh status" button): call Razorpay's Fetch Account API (`GET /accounts/{account_id}`) to pull the ground-truth status instead of trusting whatever was last stored locally. This also covers the case where activation actually happened but the webhook was delayed or missed.
6. **Razorpay reviews the KYC** (manual, commonly a few business days) before the Linked Account moves to `activated`. BatchBook learns this via a dedicated `account.activated` webhook — separate from payment webhooks. Until it fires, "Generate Payment Link" stays disabled for that institute; there's nothing to route money to yet.
7. **Once active**, every `generate_payment_link()` call for that institute attaches a `transfers` array to the Razorpay API request — ~97% routed to `institute.razorpay_linked_account_id`, ~3% retained as the platform fee. This is a per-transaction instruction, not a standing setting — there's no separate "always pay this account" call to make.
8. **Parent pays the link** → money lands in Razorpay's own nodal account → Razorpay auto-splits and auto-settles both legs directly to each party's registered bank account on its normal cycle (~T+3). BatchBook never holds or manually moves the money at any point.

---

### Task F.1 — Confirm Razorpay Route eligibility & apply for access

- [ ] Contact Razorpay support/sales to confirm current (post Sept-2025 PA-PG update) eligibility criteria for Route as a marketplace platform
- [ ] Apply for Route access on your Razorpay merchant account if not already enabled
- [ ] Confirm the Linked Account / hosted-onboarding API docs against your actual account type, in test mode first

**Verified by:** _(pending)_

---

### Task F.2 — Add a Settings page to the owner dashboard

**Why:** No Settings page exists today — needed as the home for the new Payouts section (step 2 above).

- [ ] Add `Settings` to the dashboard `NAV_ITEMS` sidebar and a corresponding route
- [ ] Add a "Payouts" section showing connection status: `Not connected` / `Setup incomplete` / `Pending verification` / `Active` / `Rejected`
- [ ] For `Setup incomplete`, show a "Continue Setup" button (resumes the same Linked Account — see Task F.3); for `Rejected`, show the rejection reason with a retry button
- [ ] On the Fees page, show a "Connect Payouts" banner the first time an owner without a connected account tries to generate a payment link (step 3 above)

**Verified by:** _(pending)_

---

### Task F.3 — Owner onboarding via Razorpay-hosted Linked Account flow

- [ ] Add nullable `razorpay_linked_account_id` and `razorpay_account_status` (enum: `not_connected` / `kyc_incomplete` / `pending_kyc` / `active` / `rejected`) columns to `InstituteSchema` — migrate with Alembic
- [ ] On "Connect Payouts": call Razorpay `POST /accounts` to create a shell Linked Account, store the returned `account_id`, set status `kyc_incomplete` (step 4 above) — if an institute already has an `account_id` in `kyc_incomplete`, reuse it instead of creating a new one
- [ ] Redirect the owner to Razorpay's hosted onboarding page for that `account_id` so Razorpay collects KYC directly
- [ ] Handle the return redirect — if KYC was actually submitted, move status to `pending_kyc`; if the owner bailed without submitting, status stays `kyc_incomplete` and "Continue Setup" re-redirects to the same `account_id` (step 5 above)
- [ ] On Settings page load (and via a manual "Refresh status" action), call Razorpay's Fetch Account API (`GET /accounts/{account_id}`) to reconcile the stored status against ground truth — don't rely solely on the redirect or the webhook, since an abandoned flow produces neither

**Verified by:** _(pending)_

---

### Task F.4 — Handle the `account.activated` webhook

**Why:** A separate webhook from payment confirmation — tells BatchBook the Linked Account passed Razorpay's KYC review and can now legally receive a split settlement (step 6 above).

- [ ] Add a Razorpay account-event webhook handler for `account.activated` and `account.rejected` (can share one route with Task F.6, keyed by event type)
- [ ] On `account.activated`: set `Institute.razorpay_account_status = "active"`, unlock "Generate Payment Link" for that institute
- [ ] On `account.rejected`: surface the reason in Settings so the owner can retry KYC

**Verified by:** _(pending)_

---

### Task F.5 — Split payments via Route on payment-link creation

- [ ] In `fee_service.py: generate_payment_link()`, add a `transfers` array to the `data` dict passed to `razorpay_client.payment_link.create()` — route ~97% to `institute.razorpay_linked_account_id`, ~3% retained as platform fee (step 7 above)
- [ ] Make the split percentage a named constant (e.g. `PLATFORM_FEE_PCT = Decimal("0.03")`) in one place, not hardcoded inline
- [ ] Reject `generate_payment_link()` calls for institutes where `razorpay_account_status != "active"`

**Verified by:** _(pending)_

---

### Task F.6 — Real Razorpay payment webhook handler

**Why:** Payment confirmation is currently 100% manual. A webhook makes the fee status update itself the moment Razorpay confirms payment (step 8 above), and unblocks the auto `fee_receipt` WATI send already planned in Task D.2.

- [ ] Add `POST /webhooks/razorpay` route (no JWT auth — verified by signature instead)
- [ ] Verify the `X-Razorpay-Signature` header against the raw request body using `razorpay_client.utility.verify_webhook_signature()` and a new `RAZORPAY_WEBHOOK_SECRET` env var
- [ ] Handle the `payment_link.paid` event: look up the `FeeRecord` by its stored `payment_link`/reference, then call the existing `fee_service.mark_payment()` logic automatically with the captured amount and Razorpay `payment.id` as the reference
- [ ] Keep `PATCH /fee/record/{id}/pay` as-is for manual/offline (cash) payments — don't remove it
- [ ] Register the webhook URL + secret in the Razorpay dashboard once deployed

**Verified by:** _(pending)_

---

### Task F.7 — End-to-end settlement test before onboarding a second real owner

- [ ] In Razorpay test mode: create a test Linked Account, run it through hosted onboarding, generate a split payment link, pay it with a test card/UPI, and confirm `account.activated` fires, the payment webhook fires, `FeeRecord` updates automatically, and the test Linked Account's ledger shows the ~97% split
- [ ] Document the actual settlement cycle time (Route via nodal account is typically T+3) somewhere visible, to set owner expectations
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
| Set up CI/CD (Task C.4) | Safe deploys going forward |
| Full smoke test on `https://batchbook.in` (Task C.5) | Confidence before real users |
| Wait for Meta Business verification approval | WATI credentials (Phase D) |
| Confirm Razorpay Route eligibility under RBI's Sept-2025 PA-PG rules (Task F.1) | Safe onboarding of any real second paying owner |

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
uv run pytest -v   # 247 tests

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
