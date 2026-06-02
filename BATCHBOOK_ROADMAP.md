# BatchBook — Complete Project Roadmap & Todo List

> **How to use this file:** Read the "Current State" section first to orient yourself. Then find the first unchecked `- [ ]` item across the phases and start there. Each step has an explanation of *why* it matters, not just what to do.

---

## What Is BatchBook?

A vertical SaaS product for India's small coaching institutes (tuition centers with 30–300 students). The target customer is a solo maths/science teacher in Gurugram/Jaipur/Lucknow who currently manages fees on WhatsApp and attendance in a paper register — spending 8–10 hrs/week on admin work that software can do in seconds.

**The product has two sides:**
1. **Owner/Teacher app** (web) — the paying customer. Manages students, batches, fees, attendance.
2. **Student app** (mobile-first web) — already partially built. Students see their attendance, schedule, fee status.

**We are building the Owner app first.**

---

## Two Repos, One Product

| Repo | Path | Stack | Status |
|------|------|-------|--------|
| Backend API | `~/PycharmProjects/BatchBook` | FastAPI + PostgreSQL (Supabase) | **Phases 1–4 + 6 INTEGRATED (221 tests). Phase 0 in progress.** |
| Frontend | `~/WebstormProjects/batchbookui` | React 19 + Material-UI | **Owner dashboard fully integrated. Student dashboard wired to real APIs (Phase 0). Teacher dashboard is a stub (deferred).** |

---

## Current State (as of June 2026)

### Backend — What Works Today
- `Owner`, `Institute`, `Teacher`, `Parent`, `Student` models all in the database with migrations applied
- `Batch` + `BatchTeacher` models — owner can create and manage batches; teachers can be assigned
- `Enrollment` model — students linked to batches with per-student due dates
- `FeeStructure` + `FeeRecord` models — monthly fee config per batch, per-student fee tracking (NOT_PAID / PARTIALLY_PAID / FULLY_PAID)
- `ClassSession` + `Attendance` models — session creation pre-populates ABSENT rows, bulk_mark sets PRESENT
- `TestScore` model — owners record test scores; `needs_attention` flag auto-fires when last-3-test avg < 60%
- OTP-based login for Owner, Student/Parent, Teacher via Supabase Auth
- Global request logging middleware (loguru) + 500 JSON error handler
- **221 tests passing** (pytest) across auth, owner, fee, attendance, test score services and routes

### Backend — What Is Missing
- No Razorpay UPI payment link generation (Task 3.3) — **needs your Razorpay API keys**
- No WhatsApp fee reminders or absence alerts via WATI (Tasks 3.4, 4.2) — **needs your WATI credentials + template approval**
- No student-facing read APIs for the student dashboard (Task 5.1)

### Frontend — What Works Today
- Firebase removed; Supabase OTP auth wired in `PhoneLogin.jsx` + `OtpVerification.jsx`
- `AuthContext` + `api.js` (axios with auto-JWT) in place
- Owner dashboard with sidebar nav: **Batches, Students, Fees, Attendance, Tests** pages all built
- `FeesPage` — month selector, 4 summary cards, per-batch fee table with Remind / Mark Paid buttons
- `AttendancePage` + `MarkAttendanceSheet` — session creation, PRESENT/ABSENT toggles
- `TestsPage` — score entry modal, score table, `needs_attention` flag display
- `ErrorBoundary` + global MUI toast on API errors

### Frontend — What Is Missing
- Student dashboard still uses **mock data** — not connected to real backend APIs (Phase 5)
- `OwnerDashboard` header stats ("X students enrolled | ₹Y collected | Z% avg attendance") not wired up — needs fee + attendance APIs (partial Task 6.3)

### Known Integration Gaps (fixed in Phase 0)
- **ProtectedRoute had no role enforcement** — any logged-in user could reach any dashboard by URL. Fix: Task 0.1 adds OwnerRoute + StudentRoute with session + role checks.
- **Owner post-login skipped institute creation** — new owner went straight to dashboard, causing API failures. Fix: Task 0.2 checks institute existence after OTP and routes to /owner/setup if missing.
- **Parent OTP called wrong endpoint** — PhoneOtpStep called /student/verify_otp; correct is /parent/verify_otp. Fix: Task 0.4 corrects the endpoint and stores the student ID for dashboard queries.
- **Student dashboard was 100% mock data on master** — PR #22 was a draft, never merged. Fix: Task 0.3 rewrites dashboardService.js and wires StudentDashboard.jsx to real backend.
- **Teacher option in OnboardingWizard routed to a non-functional dashboard** — teacher scope is deferred. Fix: Teacher option is disabled with a "Coming soon" tooltip.

---

## Architecture — How the Pieces Fit Together

```
[Owner's Browser]              [Student's Phone Browser]
       |                                |
  /owner/* routes               /student/* routes
       |                                |
       └──────────── React App ─────────┘
                         |
                    api.js (axios)
                    Supabase JWT token in every request header
                         |
                    FastAPI Backend (port 8000)
                         |
               ┌─────────┴──────────┐
          Supabase Auth         PostgreSQL DB
          (OTP + JWT)           (all data)
```

### Database Relationships (read this before touching any models)

```
Owner ──────────────── Institute (one owner has one institute)
Institute ──────────── Teacher (one institute has many teachers; owner invites via phone → OTP)
Institute ──────────── Batch (one institute has many batches, e.g. "Class 10 Maths 4PM")
Batch ──────────────── BatchTeacher (many-to-many: two teachers can share one batch)
Teacher ────────────── BatchTeacher
Batch ──────────────── Enrollment (one batch has many enrollments)
Parent ──────────────── Student (one parent can have multiple children enrolled; parent holds phone + auth)
Student ────────────── Enrollment (one student can be in multiple batches)
Enrollment ─────────── FeeRecord (one enrollment has one fee record per month)
Batch ──────────────── FeeStructure (one batch has one fee structure — monthly amount only)
Batch ──────────────── ClassSession (one batch has many class sessions)
ClassSession ────────── Attendance (one session has one attendance row per enrolled student)
```

**Key design decisions:**
- `Parent` holds the phone number and Supabase auth — the "student app" is actually a parent app. One parent can see all their children.
- `due_day` and `first_month_amount` live on `Enrollment`, not `FeeStructure` — students joining mid-month each have their own due date.
- `BatchTeacher` is a join table — a teacher can teach multiple batches, a batch can have multiple teachers.
- `Batch.status` lifecycle: `ACTIVE → CLOSING` (auto, when end_date passes) `→ ARCHIVED` (manual, only when all fee records settled).

---

## Roadmap Overview

| Phase | Goal | Status |
|-------|------|--------|
| **0** | Integration stabilization — role routing, setup gate, student live data | ⬜ NOT-STARTED (in progress) |
| **1** | Foundation: fix auth, create Owner model, basic owner dashboard shell | ✅ INTEGRATED |
| **2** | Core data: Batch + Enrollment, student management UI | ✅ INTEGRATED |
| **3** | Fee Management MVP (the product people pay for) | 🟡 PARTIAL — 3.1 ✅ 3.2 ✅ 3.3 ✅ 3.5 ✅ · 3.4 🚫 BLOCKED (WATI) |
| **4** | Attendance + WhatsApp parent alerts | 🟡 PARTIAL — 4.1 ✅ 4.3 ✅ 4.4 ✅ · 4.2 🚫 BLOCKED (WATI) |
| **5** | Connect student app to real backend | ⬜ NOT-STARTED (covered by Phase 0.3) |
| **6** | Polish, tests, performance tracker | 🟡 PARTIAL — 6.1 ✅ 6.2 ✅ 6.4 ✅ · 6.3 🔧 PARTIAL |

---

## PHASE 0 — Integration Stabilization ⬜ IN PROGRESS

**What we're doing:** Fixing three integration gaps that were left when features were built in isolation. Nothing new is being built — we are making what already exists actually work together end-to-end.

**The agent MUST complete all Phase 0 tasks before picking any Phase 1–6 task.**

---

### Task 0.1 — Frontend: Role-aware routing ⬜ IN PROGRESS

**Why:** ProtectedRoute only checked session existence. Any logged-in user could reach any dashboard URL by typing it directly.

- [x] Update `AuthContext.jsx`: clean `bb_role` + `bb_student_id` from localStorage on signOut and session expiry
- [x] Create `OwnerRoute.jsx`: session + `role === 'owner'` required (reads localStorage directly); else → `/phone-login`
- [x] Create `StudentRoute.jsx`: session + `role === 'student'` required (reads localStorage directly); else → `/onboarding`
- [x] Update `OtpVerification.jsx`: after setSession, stamp `localStorage.setItem('bb_role', 'owner')`
- [x] Update `PhoneOtpStep.jsx`: call `/parent/verify_otp` (not `/student/verify_otp`); stamp `bb_role = 'student'` and `bb_student_id = children[0].id`
- [x] Update `RoleStep.jsx`: disable teacher option with "Coming soon" tooltip
- [x] Update `App.jsx`: `/owner/*` → OwnerRoute, `/dashboard/student` → StudentRoute, `/dashboard/teacher` → static message

**Verified by:** _(pending manual verification)_

---

### Task 0.2 — Frontend: Owner setup gate ⬜ IN PROGRESS

**Why:** A new owner (no institute yet) who completes OTP was sent directly to `/owner/dashboard`. Every API call that needs `institute_id` silently failed.

- [x] Update `OtpVerification.jsx`: after setSession and role stamp, call `GET /owner/institute`. Navigate to `/owner/setup` on 404, `/owner/dashboard` on 200.

**Verified by:** _(pending manual verification)_

---

### Task 0.3 — Backend + Frontend: Student dashboard live data ⬜ IN PROGRESS

**Why:** `dashboardService.js` on master was 100% hardcoded mock data.

**Backend is already done** — `student_dashboard_route.py` is implemented and registered.

- [x] Rewrite `dashboardService.js` to call `/parent/me`, `/student/me/attendance`, `/student/me/schedule`, `/student/me/upcoming-events` via `api.js`
- [x] Replace `PlaceholderContent` in `StudentDashboard.jsx` with real data display

> **Note:** Task 0.3 covers the same work as Phase 5 (Tasks 5.1 + 5.2). Mark Phase 5 Tasks 5.1 and 5.2 as ✅ INTEGRATED once Task 0.3 is verified.

**Verified by:** _(pending manual verification)_

---

## PHASE 1 — Foundation ✅ Complete

**What we're doing:** Rip out Firebase from the frontend, plug in Supabase instead, create the Owner + Parent + Teacher models in the backend, and build the bare skeleton of the owner dashboard.

**Why this must come first:** Every other feature needs authenticated users. The Owner model lets the institute owner log in. The Parent model correctly handles the student-app login (parents log in, see their children). The Teacher model lets hired teachers mark attendance independently. Firebase + Supabase doing the same job is a bug waiting to happen — one auth source of truth.

---

### Task 1.1 — Backend: Add CORS + Owner model

- [x] **Add CORS to `app.py`**
- [x] **Create `BatchBook/models/owner_base.py`**
- [x] **Create Alembic migration**
- [x] **Create `BatchBook/repositories/owner_repository.py`**
- [x] **Create `BatchBook/services/owner_service.py`**
- [x] **Create `BatchBook/routes/owner_route.py`**
- [x] **Register router in `app.py`**
- [x] **Smoke test:** Use the FastAPI `/docs` page (`http://localhost:8000/docs`) to send OTP to your phone and verify it. You should get back a JWT token.

---

### Task 1.2 — Backend: Institute model

- [x] **Create `BatchBook/models/institute_base.py`**
  Fields: `id` (int, PK), `owner_id` (FK → owner.id), `name` (str), `city` (str), `created_at` (datetime)

- [x] **Create migration and run it**

- [x] **Create `BatchBook/repositories/institute_repository.py`**
  Functions: `create(db, data)`, `get_by_owner_id(db, owner_id)`, `update(db, institute, updates)`

- [x] **Add 2 endpoints to `owner_route.py`**
  - `POST /owner/institute` — owner sets up their institute (name, city). Only allowed once per owner.
  - `GET /owner/institute` — get the owner's institute details.

---

### Task 1.3 — Backend: Parent model + refactor Student model

- [x] **Create `BatchBook/models/parent_base.py`**
- [x] **Refactor `BatchBook/models/student_base.py`**
- [x] **Create migration and run it**
- [x] **Create `BatchBook/repositories/parent_repository.py`**
- [x] **Refactor `BatchBook/services/student_service.py`**
- [x] **Update student auth routes**

---

### Task 1.4 — Backend: Teacher model + auth

- [x] **Create `BatchBook/models/teacher_base.py`**
- [x] **Create migration and run it**
- [x] **Create `BatchBook/repositories/teacher_repository.py`**
- [x] **Create `BatchBook/services/teacher_service.py`**
- [x] **Create `BatchBook/routes/teacher_route.py`**
- [x] **Register router in `app.py`**

---

### Task 1.5 — Frontend: Remove Firebase, add Supabase

- [x] **Remove Firebase** — `firebase` package uninstalled, `src/firebaseconfig.ts` deleted.
- [x] **Install Supabase JS client**
- [x] **Create `src/lib/supabaseClient.js`**
- [x] **Create `src/context/AuthContext.jsx`**
- [x] **Rewrite `src/components/PhoneLogin.jsx`** — uses `supabase.auth.signInWithOtp`
- [x] **Rewrite `src/components/OtpVerification.jsx`** — uses `supabase.auth.verifyOtp`
- [x] **Wrap `App.jsx` in `<AuthProvider>`**
- [x] **Add protected route**

---

### Task 1.6 — Frontend: Owner routes + basic dashboard shell

- [x] **Create `src/services/api.js`** — axios instance with auto-JWT interceptor
- [x] **Add owner routes to `App.jsx`**
- [x] **Create `src/pages/owner/OwnerSetup.jsx`**
- [x] **Create `src/pages/owner/OwnerDashboard.jsx`** — sidebar with Batches, Students, Fees, Attendance, Tests
- [x] **End-to-end test:** Phone login → OTP → owner dashboard, no Firebase/CORS errors

---

## PHASE 2 — Core Data Models ✅ Complete

---

### Task 2.1 — Backend: Batch model + CRUD APIs

- [x] **Create `BatchBook/models/batch_base.py`**
- [x] **Create `BatchBook/models/batch_teacher_base.py`**
- [x] **Create migration and run it**
- [x] **Create `BatchBook/repositories/batch_repository.py`**
- [x] **Create `BatchBook/services/batch_service.py`**
- [x] **Create `BatchBook/routes/batch_route.py`** with 7 endpoints (create, list, get, update, delete, assign-teacher, archive)
- [x] Register router in `app.py`

---

### Task 2.2 — Backend: Enrollment model (student ↔ batch link)

- [x] **Add `institute_id` (nullable FK) to StudentSchema**
- [x] **Create `BatchBook/models/enrollment_base.py`**
- [x] **Create migration and run it**
- [x] **Create `BatchBook/repositories/enrollment_repository.py`**
- [x] **Create `BatchBook/routes/enrollment_route.py`** with 4 endpoints
- [x] Register router in `app.py`

---

### Task 2.3 — Frontend: Batch management + Student list pages

- [x] **Create `src/services/ownerService.js`**
- [x] **Create `src/pages/owner/BatchesPage.jsx`**
- [x] **Create `src/pages/owner/CreateBatchModal.jsx`**
- [x] **Create `src/pages/owner/StudentsPage.jsx`**
- [x] **Create `src/pages/owner/AddStudentModal.jsx`**
- [x] **Wire pages into `OwnerDashboard.jsx`** sidebar navigation

---

## PHASE 3 — Fee Management MVP 🟡 Partial

**What we're doing:** The core product. An owner can set a monthly fee per batch, see who has and hasn't paid for a given month, send WhatsApp reminders to defaulters, mark cash/UPI payments, and generate receipts.

---

### Task 3.1 — Backend: FeeStructure + FeeRecord models ✅

- [x] **Create `BatchBook/models/fee_structure_base.py`**
- [x] **Create `BatchBook/models/fee_record_base.py`**
- [x] **Create migrations and run them**
- [x] **Create `BatchBook/repositories/fee_repository.py`**
- [x] **Create `BatchBook/services/fee_service.py`**

---

### Task 3.2 — Backend: Fee API routes ✅

- [x] **Create `BatchBook/routes/fee_route.py`** with endpoints:
  - `POST /fee/structure`, `POST /fee/generate/{batch_id}`, `PATCH /fee/record/{record_id}/pay`, `GET /fee/dashboard`, `GET /fee/batch/{batch_id}`
- [x] Register router in `app.py`

---

### Task 3.3 — Backend: Razorpay UPI payment links ✅

> **⚠️ Blocked on you:** Sign up at razorpay.com → Dashboard → Settings → API Keys → generate a **test key pair**. Add to `BatchBook/.env`:
> ```
> RAZORPAY_KEY_ID=rzp_test_xxxxx
> RAZORPAY_KEY_SECRET=xxxxxxxx
> ```
> The `payment_link` column is already on `FeeRecord` — this task just needs the Razorpay client and one new endpoint.
> Hi Bedant sharma this side (the owner of this repo) i have added the razorpay creds in my local env file so you can contniue the further developeent assuming that there are razorpay creds

- [x] **Sign up for Razorpay** and add test keys to `.env`
- [x] **Add razorpay to `pyproject.toml`** and install: `uv add razorpay`
- [x] **Create `BatchBook/clients/razorpay_client.py`**
- [x] **Add `GET /fee/record/{record_id}/payment-link` endpoint**

---

### Task 3.4 — Backend: WhatsApp fee reminders via WATI ❌ **NEEDS YOUR INPUT**

> **⚠️ Blocked on you:** Sign up at wati.io → get API endpoint URL + API token → add to `.env`:
> ```
> WATI_API_ENDPOINT=https://live-mt-server.wati.io/XXXXX
> WATI_API_TOKEN=xxxxxxxx
> ```
> Then create 2 templates in the WATI dashboard and wait for WhatsApp approval (24–48 hrs):
> - `fee_reminder`: "Hi {{1}}, your fee of ₹{{2}} for {{3}} is due on {{4}}. Pay here: {{5}}"
> - `fee_receipt`: "Hi {{1}}, payment of ₹{{2}} received for {{3}} on {{4}}. Thank you!"

- [ ] **Sign up for WATI** and add credentials to `.env`
- [ ] **Create WhatsApp message templates in WATI dashboard** and wait for approval
- [ ] **Create `BatchBook/clients/wati_client.py`**
- [ ] **Create `BatchBook/services/notification_service.py`**
- [ ] **Add reminder endpoints to `fee_route.py`**: `POST /fee/remind/{record_id}`, `POST /fee/remind-all`
- [ ] **Auto-send receipt** after `mark_payment()` succeeds

---

### Task 3.5 — Frontend: Fee Management pages ✅

- [x] **Add fee functions to `src/services/ownerService.js`**
- [x] **Create `src/pages/owner/FeesPage.jsx`**
- [x] **Create `src/pages/owner/FeeSetupModal.jsx`**
- [x] **Create `src/pages/owner/MarkPaymentModal.jsx`**
- [x] **Smoke test:** Set up fee → generate records → NOT_PAID → Mark Paid → FULLY_PAID

---

## PHASE 4 — Attendance + WhatsApp Parent Alerts 🟡 Partial

---

### Task 4.1 — Backend: ClassSession + Attendance models ✅

- [x] **Create `BatchBook/models/class_session_base.py`**
- [x] **Create `BatchBook/models/attendance_base.py`**
- [x] **Create migrations and run them**
- [x] **Create `BatchBook/services/attendance_service.py`**
  - `create_session()` — creates session + pre-populates ABSENT rows for all active enrollments
  - `bulk_mark()` — idempotent; given IDs → PRESENT, rest → ABSENT
  - `get_student_attendance_summary()` — {present, total, percentage} per month

---

### Task 4.2 — Backend: Absence WhatsApp alert ❌ **NEEDS YOUR INPUT**

> **⚠️ Blocked on WATI credentials** (same as Task 3.4). Once WATI is set up, create a third template:
> - `absence_alert`: "Hi, {{1}} was absent from {{2}} today ({{3}}). Please contact us if this is unexpected."

- [ ] **Add to `BatchBook/services/notification_service.py`**: `send_absence_alert(enrollment_id, date)`
- [ ] **Hook into `bulk_mark()`**: after marking absences, call `send_absence_alert` async for each absent enrollment

---

### Task 4.3 — Backend: Attendance routes ✅

- [x] **Create `BatchBook/routes/attendance_route.py`**:
  - `POST /attendance/session`, `POST /attendance/session/{session_id}/mark`, `GET /attendance/session/{session_id}`, `GET /attendance/batch/{batch_id}`, `GET /attendance/student/{enrollment_id}`
- [x] Register router in `app.py`

---

### Task 4.4 — Frontend: Attendance pages ✅

- [x] **Create `src/pages/owner/AttendancePage.jsx`** — date picker, batch selector, session list, Start Session button
- [x] **Create `src/pages/owner/MarkAttendanceSheet.jsx`** — PRESENT/ABSENT toggles, Mark All Present shortcut, Submit button

---

## PHASE 5 — Connect Student App to Real Backend ❌ Not started

**What we're doing:** All the mock data in the student-facing dashboard gets replaced with real API calls. Rahul logs in and sees his actual 18/22 attendance, his actual ₹1500 fee status, and tomorrow's actual session.

---

### Task 5.1 — Backend: Student-facing read APIs

- [ ] **Create `BatchBook/routes/student_dashboard_route.py`**:
  - `GET /student/me/attendance?month=2026-05`
  - `GET /student/me/fee?month=2026-05`
  - `GET /student/me/schedule?date=2026-05-05`
  - `GET /student/me/upcoming-events?limit=10`
- [ ] Register router in `app.py`

---

### Task 5.2 — Frontend: Replace mock data in student dashboard

- [ ] **Rewrite `src/services/dashboardService.js`** — replace every mock `setTimeout` with real `api.js` calls
- [ ] **Update `src/components/Dashboard.jsx`** — loading states, error handling, fee alert banner with real Razorpay link
- [ ] **End-to-end test:** Student logs in → real attendance → real schedule → real fee status

---

## PHASE 6 — Polish, Tests & Performance Tracker 🟡 Partial

---

### Task 6.1 — Backend: Tests ✅

**221 tests passing** across all domains.

- [x] **Set up pytest with async support** — `pytest-asyncio`, `httpx`, `aiosqlite` in `pyproject.toml`
- [x] **Create `tests/conftest.py`** with `test_db` + `client` fixtures
- [x] **Write `tests/test_fee_service.py`** — generate_monthly_records, mark_payment status transitions, edge cases
- [x] **Write `tests/test_attendance_service.py`** — create_session pre-populates ABSENT, bulk_mark correctness
- [x] **Write `tests/test_auth_service.py` + auth route tests** — 401 on missing/invalid token
- [x] Run: `uv run pytest -v` — all 221 tests pass

---

### Task 6.2 — Backend: Performance tracker ✅

- [x] **Create `BatchBook/models/test_score_base.py`**
- [x] **Create migration + repo + service** — `add_score()` with validation; `get_scores_for_enrollment()` with `needs_attention` flag (avg of last 3 < 60%)
- [x] **Create endpoints**: `POST /scores/` and `GET /scores/student/{enrollment_id}`

---

### Task 6.3 — Frontend: Performance tab + analytics 🟡 Partial

- [x] Add "Tests" to owner sidebar
- [x] Create score entry form (batch/student selector, test name, subject, max marks, obtained marks)
- [x] Create student score table with `needs_attention` badge
- [ ] **Add to `OwnerDashboard.jsx` header: "X students enrolled | ₹Y collected this month | Z% avg attendance"** — needs fee dashboard + attendance summary API calls wired in

---

### Task 6.4 — Error handling & stability ✅

- [x] **Backend: Global exception handler + request logging middleware in `app.py`** — loguru logs every request (method, path, status, elapsed); unhandled exceptions → 500 JSON
- [x] **Frontend: Error boundary** — `src/components/ErrorBoundary.jsx` wraps entire app; shows "Something went wrong" + retry button
- [x] **Frontend: Global error toast** — `ToastContext` + `toastEmitter`; non-401 API errors show MUI Snackbar

---

## ⚠️ What Needs Your Input Right Now

These tasks are **blocked on external credentials** — the agent cannot do them without you signing up first:

| Task | What you need to do | Unlocks |
|------|---------------------|---------|
| **3.3** — Razorpay payment links | Sign up at razorpay.com → get test API key pair → add to `.env` | Parents can pay fees with one click |
| **3.4** — WhatsApp fee reminders | Sign up at wati.io → get API token → create 2 templates → wait 24–48h for approval | Bulk fee reminder and receipt messages |
| **4.2** — WhatsApp absence alerts | Same WATI setup as 3.4 + create `absence_alert` template | Auto-WhatsApp to parents when student is absent |

Once you have those credentials, the next autonomous session can implement all three in one run.

---

## External Services Setup Checklist

- [x] **Supabase:** Configured. Anon key in frontend `.env`, service key in backend `.env`
- [ ] **Razorpay:** Sign up at razorpay.com → get test API key → add to backend `.env`
- [ ] **WATI:** Sign up at wati.io → get API endpoint + token → add to backend `.env` → create 3 templates (fee_reminder, fee_receipt, absence_alert) → wait for WhatsApp approval

---

## Environment Variables Reference

**Backend `BatchBook/.env`:**
```
PROJECT_NAME=BatchBook
DATABASE_URL=postgresql+asyncpg://[user]:[password]@[host]/postgres
SUPABASE_URL=https://[project-id].supabase.co
SUPABASE_KEY=sb_publishable_[key]
RAZORPAY_KEY_ID=rzp_test_xxxxx          # Add for Task 3.3
RAZORPAY_KEY_SECRET=xxxxxxxx             # Add for Task 3.3
WATI_API_ENDPOINT=https://live-mt-server.wati.io/XXXXX  # Add for Tasks 3.4 + 4.2
WATI_API_TOKEN=xxxxxxxx                  # Add for Tasks 3.4 + 4.2
```

**Frontend `batchbookui/.env`:**
```
VITE_SUPABASE_URL=https://[project-id].supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGci...
```

---

## How to Run the Projects

**Backend (Docker — preferred):**
```bash
make dev          # start frontend + backend with hot-reload
make dev-d        # same but detached
make logs-b       # tail backend logs
```

**Backend (without Docker):**
```bash
cd ~/PycharmProjects/BatchBook
uv run uvicorn app:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

**Frontend:**
```bash
cd ~/WebstormProjects/batchbookui
npm run dev       # http://localhost:5173
```

**Tests:**
```bash
cd ~/PycharmProjects/BatchBook
uv run pytest -v  # 221 tests
```

---

## Quick Reference: Key Files

| What you want to change | File to open |
|-------------------------|-------------|
| Add a new API endpoint | `BatchBook/routes/<domain>_route.py` |
| Add business logic | `BatchBook/services/<domain>_service.py` |
| Add a DB query | `BatchBook/repositories/<domain>_repository.py` |
| Add a new DB table | `BatchBook/models/<name>_base.py` + run alembic |
| Add env variable | `BatchBook/config.py` (add field to Settings class) + `.env` |
| Add a new frontend page | `batchbookui/src/pages/owner/<PageName>.jsx` |
| Add a new API call | `batchbookui/src/services/ownerService.js` |
| Change the auth token logic | `batchbookui/src/services/api.js` |
| Change global auth state | `batchbookui/src/context/AuthContext.jsx` |

---

## Status Labels

| Symbol | Label | Meaning |
|--------|-------|---------|
| ✅ | `INTEGRATED` | PR merged to master, feature manually verified working |
| 🟡 | `PR-OPEN` | Code written, PR exists, not yet merged to master |
| 🔧 | `PARTIAL` | Some sub-tasks merged and working, others missing |
| ⬜ | `NOT-STARTED` | Not touched |
| 🚫 | `BLOCKED` | Waiting on external credential, API access, or template approval |

---

## Definition of INTEGRATED (for agentic workers)

A task is only marked ✅ INTEGRATED when ALL four conditions are true:

1. **PR merged to master** — not open, not draft. Actually merged.
2. **Tests pass** — `uv run pytest -v` shows zero failures after the merge.
3. **Feature manually verified:**
   - Backend task: at least one real curl/httpie request hit the endpoint and returned expected data. Include the command + output in the PR description.
   - Frontend task: describe what a user sees when the feature works correctly.
4. **This roadmap task has a "Verified by:" line** written in its checklist.

**Marking a task INTEGRATED when its PR is open or draft is a roadmap bug. Do not do it.**

---

## Nightly Agent Pre-flight

Run every session, before picking any task:

```
1. git checkout master && git pull origin master
2. grep -rn "<<<<<<" --include="*.py" --include="*.jsx" --include="*.js" .
   → If anything found: fix conflicts, open PR, end session. No new tasks.
3. uv run pytest -q
   → If tests fail: fix them, open PR, end session. No new tasks.
4. Find the most recently modified task in this file.
   → If it is PR-OPEN: write in session summary "PR [#N] needs merge before next task." End session.
   → If it is INTEGRATED: proceed to step 5.
5. Pick the first ⬜ NOT-STARTED task (top to bottom). Skip 🚫 BLOCKED.
   Phase 0 tasks take priority over all other phases.
```

# todo for later - 
> 1.  getStudentProfile() makes 3 concurrent API calls — if any fail, the whole load errors. Consider splitting into independent loading states in a future iteration.
> 2. Multi-child parents see the first child automatically. A child-selector could be added later.
> 3. The streak field in attendance is hardcoded to 0 — no streak computation endpoint exists yet.