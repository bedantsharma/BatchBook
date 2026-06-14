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
- **nginx.conf only proxies `/student/*` and `/owner/*`** — every call to `/batch/*`, `/fee/*`, `/attendance/*`, `/enrollment/*`, `/scores/*`, `/parent/*` would 404. The entire owner dashboard breaks in prod.
- **No domain, no SSL, no hosting** — Docker prod stack exists but nowhere to run it

### What is incomplete (code partially written or missing)
- `OwnerDashboard` header stats ("X students enrolled | ₹Y collected | Z% avg attendance") — backend `/owner/stats` exists but frontend not wired
- Student dashboard: only "Overview" tab works; Batches/Schedule/Fees tabs show greyed-out with `cursor: not-allowed`
- Student fee payment button (Razorpay link) never surfaced in student dashboard
- Attendance streak hardcoded to 0 (no backend endpoint)
- Notification count always returns 0 (no backend endpoint)
- Landing page is a placeholder card — not a real marketing page

### What is blocked on external credentials
- WATI tasks (3.4, 4.2) — pending Meta/WhatsApp Business verification, which itself is blocked because WATI needs a business website URL

---

## Gap Summary Table

| Gap | Severity | Blocks |
|-----|----------|--------|
| nginx only proxies 2 of 9 route prefixes | 🔴 CRITICAL | All of owner dashboard in prod |
| No hosting/domain/SSL | 🔴 CRITICAL | Deployment |
| WATI needs a business website URL for Meta | 🔴 CRITICAL | WhatsApp notifications |
| Owner header stats not wired | 🟡 HIGH | UX completeness |
| Student Batches/Schedule/Fees tabs greyed out | 🟡 HIGH | Student app completeness |
| Student Razorpay payment link not surfaced | 🟡 HIGH | Core value prop for parents |
| Phase 0 flows never manually tested | 🟡 HIGH | Confidence before launch |
| No CI/CD pipeline | 🟡 HIGH | Safe deployments |
| Landing page is placeholder | 🟠 MEDIUM | WATI verification + user acquisition |
| Attendance streak always 0 | 🟠 MEDIUM | Student UX |
| Multi-child parent has no child selector | 🟠 MEDIUM | Parents with >1 child |
| E2E tests never run in CI | 🟠 MEDIUM | Regression safety |
| No PDF fee receipt | 🟢 LOW | Nice-to-have |

---

## Roadmap Overview

| Phase | Goal | Status |
|-------|------|--------|
| **A** | Fix ship-blockers — nginx, stats, student tabs | ⬜ NOT-STARTED |
| **B** | Landing page (real marketing page + WATI website URL) | ⬜ NOT-STARTED |
| **C** | Deployment — hosting, domain, SSL, CI/CD | ⬜ NOT-STARTED |
| **D** | WATI notifications (fee reminders, absence alerts) | 🚫 BLOCKED (credentials) |
| **E** | Polish — multi-child, streak, receipts, E2E CI | ⬜ NOT-STARTED |

**Sequencing rationale:**
- Phase A first: fix what's broken before putting it in front of anyone
- Phase B second: landing page serves double duty — WATI needs a URL, owners need a place to find you
- Phase C third: now you have something worth deploying
- Phase D whenever: WATI credentials may arrive any time; implement immediately when they do
- Phase E ongoing: polish after real users give feedback

---

## PHASE A — Fix Ship-Blockers ⬜ NOT-STARTED

---

### Task A.1 — Fix nginx.conf to proxy all API route prefixes

**Why this is critical:** In the Docker prod stack, the React app is served by nginx. nginx proxies API calls to the FastAPI backend. The current config only proxies `/student/*` and `/owner/*`. Every owner dashboard action (create batch, mark fee, take attendance) hits `/batch/*`, `/fee/*`, `/attendance/*`, `/enrollment/*`, `/scores/*` — all of which nginx currently serves as 404s. The entire owner dashboard breaks in production.

- [ ] Update `batchbookui/nginx.conf` — extend the proxy location regex to cover all backend prefixes:
  ```nginx
  location ~ ^/(student|owner|batch|fee|attendance|enrollment|scores|parent|teacher|docs|redoc|openapi\.json)(/.*)?$ {
  ```
- [ ] Verify: `make prod` → open `http://localhost` → owner login → create a batch → confirm no 404s in browser network tab

**Verified by:** _(pending)_

---

### Task A.2 — Wire OwnerDashboard header stats

**Why:** The dashboard header currently shows no live data. An owner opening their app for the first time sees a blank header instead of "12 students enrolled | ₹8,400 collected | 87% avg attendance" — the numbers that prove the product is working.

**Backend is already done** — `GET /owner/stats` exists and returns `{ total_students, fee_collected_this_month, avg_attendance_pct }`.

- [ ] In `OwnerDashboard.jsx`: add a `useEffect` on mount that calls `GET /owner/stats` via `ownerService.js`
- [ ] Add `getOwnerStats()` to `ownerService.js` if not already there
- [ ] Render the 3 stats in the dashboard header bar
- [ ] Handle loading state (show `—` while fetching) and error state (silently hide the bar)

**Verified by:** _(pending)_

---

### Task A.3 — Manual end-to-end verification of Phase 0 flows

**Why:** Three critical flows have code written but were never tested against a running app. They could be broken in subtle ways (wrong endpoint, wrong localStorage key, redirect loops).

Run the following test scripts against `make dev` (local Docker):

- [ ] **Owner new-user flow:** Fresh phone number → `/onboarding` → select Owner → OTP → verify OTP → should land at `/owner/setup` (not `/owner/dashboard`). Complete setup → should land at `/owner/dashboard`.
- [ ] **Owner returning-user flow:** Known owner phone → OTP → should skip setup and go straight to `/owner/dashboard`.
- [ ] **Student/parent flow:** Parent phone → `/onboarding` → select Student → fill parent details → OTP → should land at `/dashboard/student` with real data (not error screen).
- [ ] **Role guard test:** Log in as owner → try navigating to `/dashboard/student` by URL → should redirect to `/phone-login`. Log in as parent → try `/owner/dashboard` → should redirect to `/onboarding`.
- [ ] **Sign out:** Click sign out → localStorage `bb_role` and `bb_student_id` should be cleared → protected routes should redirect.

For each flow, write what you saw under "Verified by" in this file.

**Verified by:** _(pending — must be done by Bedant manually)_

---

### Task A.4 — Surface Razorpay payment link in student dashboard

**Why:** Razorpay backend is done. But parents who see "Fee Due" in the student dashboard have no button to pay. The core value prop — one-click fee payment — is invisible.

- [ ] In `dashboardService.js`, add `getFeeStatus()` (already exists — check it returns `{ payment_link }` field)
- [ ] In `StudentDashboard.jsx` Overview tab: if `feeDue === true`, show a "Pay Now" button that opens `payment_link` in a new tab
- [ ] If `payment_link` is null (owner hasn't generated it yet), show "Contact your institute" instead of a broken button

**Verified by:** _(pending)_

---

### Task A.5 — Wire student Batches, Schedule, and Fees tabs

**Why:** The student sidebar shows 4 tabs (Overview, Batches, Schedule, Fees) but 3 of them are `cursor: not-allowed` stubs. A parent who taps "Schedule" and sees nothing will think the app is broken.

- [ ] Create `BatchesTab.jsx` inside `components/student/` — calls `GET /student/me/attendance` (already fetched in Overview) and lists batch names, subjects, and monthly attendance %
- [ ] Create `ScheduleTab.jsx` — calls `getTodaySchedule()` and `getUpcomingEvents()` (already fetched), displays them in a list grouped by day
- [ ] Create `FeesTab.jsx` — calls `getFeeStatus()`, shows current month status per batch, "Pay Now" button if `payment_link` present
- [ ] In `StudentDashboard.jsx`: replace `cursor: not-allowed` stubs with real content components; track `activeTab` state and render the right component

**Verified by:** _(pending)_

---

## PHASE B — Real Landing Page ⬜ NOT-STARTED

**Why this comes before deployment:** Two reasons:
1. WATI (WhatsApp Business API) requires a business website URL during Meta verification. The current placeholder card at `/` doesn't count — Meta looks for a real page with product description, privacy policy, and contact info.
2. When an owner hears about BatchBook (word of mouth, Google search), they need to land somewhere that convinces them to sign up.

---

### Task B.1 — Build a real marketing landing page

**Replace** `src/components/LandingPage.jsx` with a proper page. It does not need to be fancy — it needs to communicate clearly.

Required sections:

- [ ] **Hero:** "Run your coaching institute from your phone. Fees, attendance, tests — all in one place." + "Get Started Free" CTA button → `/onboarding`
- [ ] **3 feature cards:** (1) Fee management — collect fees, send reminders; (2) Attendance — mark in 30 seconds, parents get alerts; (3) Test scores — track who needs attention
- [ ] **How it works:** 3 steps: Sign up → Add students → Start managing (with simple icons)
- [ ] **Social proof placeholder:** "Join 50+ coaching institutes" (change the number when you have real data)
- [ ] **Footer:** BatchBook © 2026 · Privacy Policy link · Contact email (bedant's email or a hello@ alias)
- [ ] **Privacy Policy page** at `/privacy-policy` — required by Meta for WATI verification. Must state: what data you collect (phone numbers, student attendance), how it's used, that you don't sell it. A simple one-paragraph page is fine.
- [ ] **Add `/privacy-policy` route in `App.jsx`**

Design guidance:
- Reuse the existing dark theme from `App.jsx` (dark background, purple primary)
- Mobile-first — target user is on a phone
- No animations needed, no parallax — keep it fast
- Keep it in `src/components/LandingPage.jsx` (don't create a new file unless the file gets unwieldy)

**Verified by:** _(pending — visual check in browser)_

---

### Task B.2 — Deploy landing page to get a real URL

**Why:** Before the full Docker deployment, get `yourdomain.com` serving the landing page so you can submit the URL to WATI immediately.

Recommended approach: **Vercel** (free, instant, auto-deploys from git push, gives HTTPS)

- [ ] Push `batchbookui` frontend to its own GitHub repo (already at `github.com/bedantsharma/batchbookui`)
- [ ] Sign up at vercel.com → "Import Project" → connect the `batchbookui` repo
- [ ] Set env vars in Vercel: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- [ ] For now, set `VITE_API_URL` to `http://localhost:8000` — the landing page doesn't call the backend, so this doesn't matter yet
- [ ] Vercel gives you a URL like `batchbookui.vercel.app` — use this as your business URL for WATI
- [ ] Later (Task C.3), point your custom domain here and update the WATI registration

**Verified by:** _(pending — URL must be live and reachable)_

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

### Task C.1 — Buy a domain

- [ ] Buy a `.com` or `.in` domain — suggestions: `batchbook.in`, `batchbook.app`, `trybatchbook.com`
- [ ] Recommended registrar: Namecheap or Google Domains
- [ ] Note the domain here once purchased: **Domain: ___________**

---

### Task C.2 — Set up Render.com for the backend

- [ ] Sign up at render.com
- [ ] "New Web Service" → connect `github.com/bedantsharma/BatchBook`
- [ ] Environment: Docker
- [ ] Dockerfile path: `./Dockerfile`
- [ ] Docker build target: `prod`
- [ ] Set all env vars in Render dashboard:
  - `DATABASE_URL`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `RAZORPAY_KEY_ID`
  - `RAZORPAY_KEY_SECRET`
  - `PROJECT_NAME=BatchBook`
- [ ] Set custom domain: `api.yourdomain.com` → Render provides a certificate automatically
- [ ] First deploy: verify `https://api.yourdomain.com/docs` loads

**Verified by:** _(pending)_

---

### Task C.3 — Configure frontend for production

- [ ] In Vercel project settings, add env var: `VITE_API_URL=https://api.yourdomain.com`
- [ ] Add custom domain in Vercel: `yourdomain.com` (naked domain) + `www.yourdomain.com`
- [ ] Update CORS in `app.py` — add your production domain to `allow_origins`
  ```python
  # Add to CORS origins list:
  "https://yourdomain.com",
  "https://www.yourdomain.com",
  ```
- [ ] Push the change → Render auto-redeploys

**Verified by:** _(pending)_

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

## PHASE D — WATI Notifications 🚫 BLOCKED (credentials)

> Implement these the moment your WATI account is approved and you have the API endpoint + token. The Meta verification will succeed once you submit the URL from Task B.2.

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
| Manually test Phase 0 flows (Task A.3) | Confidence before deployment |
| Buy a domain (Task C.1) | All of Phase C |
| Complete Render.com setup (Task C.2) | Backend in production |
| Submit WATI business website URL (from B.2 Vercel deploy) | WATI Meta verification |

---

## Deployment Architecture (target)

```
yourdomain.com (Vercel — CDN, auto-HTTPS)
       │
       ├── / through /owner/* → React SPA (Vercel edge)
       │
       └── /batch/*, /fee/*, /attendance/*, ...
             ↓ (Vercel rewrites or direct browser calls)
    api.yourdomain.com (Render.com — always-on, $7/mo)
             │
     FastAPI + uvicorn (2 workers)
             │
      ┌──────┴──────┐
 Supabase Auth   Supabase PostgreSQL
 (OTP + JWT)     (all data)
```

> **Note on Vercel + backend calls:** The current `batchbookui/nginx.conf` is only used in the Docker prod stack. On Vercel, API calls go directly from the browser to `api.yourdomain.com` — nginx doesn't proxy them. CORS in `app.py` covers this.

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
