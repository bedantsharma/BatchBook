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
| Backend API | `~/PycharmProjects/BatchBook` | FastAPI + PostgreSQL (Supabase) | Partial — Student auth works |
| Frontend | `~/WebstormProjects/batchbookui` | React 19 + Material-UI | Partial — Student dashboard (all mock data) |

---

## Current State (as of May 2026)

### Backend — What Works Today
- `Student` model in the database (name, phone, email, fees_status, user_id)
- OTP-based login via **Supabase Auth** (send OTP to phone → verify → get JWT token)
- 5 working API endpoints:
  - `POST /student/generate_otp` — sends SMS OTP
  - `POST /student/verify_otp` — verifies OTP, creates student record, returns JWT
  - `GET /student/me` — get logged-in student's profile
  - `PATCH /student/update` — update student profile
  - `POST /student/` — create student directly (admin use)

### Backend — What Is Missing
- No `Owner` model (the teacher/institute owner can't log in yet)
- No `Batch` model (classes don't exist yet)
- No `Enrollment` model (can't link students to batches)
- No `FeeStructure` / `FeeRecord` models (the core product doesn't exist)
- No `ClassSession` / `Attendance` models
- No CORS headers (frontend can't talk to backend)
- No tests whatsoever

### Frontend — What Works Today
- Phone number input → OTP → Dashboard flow (using **Firebase** auth — to be replaced)
- Student-facing dashboard with 3 tabs: Home, Schedule, Profile
- Dark theme with purple/cyan color scheme
- Beautiful UI — but **all data is hardcoded mock data** (no real backend calls)

### Frontend — What Is Missing
- Firebase must be removed and replaced with Supabase (to match backend auth)
- Owner app doesn't exist yet — no pages, no routes, nothing
- Student dashboard is not connected to any real API

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
Owner ──────────── Institute (one owner has one institute)
Institute ─────── Batch (one institute has many batches, e.g. "Class 10 Maths 4PM")
Batch ─────────── Enrollment (one batch has many enrollments)
Student ────────── Enrollment (one student can be in multiple batches)
Batch ─────────── FeeStructure (one batch has one fee config, e.g. ₹1500/month due on 5th)
Enrollment ─────── FeeRecord (one enrollment has one fee record per month)
Batch ─────────── ClassSession (one batch has many class sessions, one per day taught)
ClassSession ───── Attendance (one session has one attendance row per enrolled student)
```

---

## Roadmap Overview

| Phase | Goal | Estimated Weeks | Hours Needed |
|-------|------|----------------|--------------|
| **1** | Foundation: fix auth, create Owner model, basic owner dashboard shell | Weeks 1–3 | ~25 hrs |
| **2** | Core data: Batch + Enrollment, student management UI | Weeks 4–5 | ~20 hrs |
| **3** | Fee Management MVP (the product people pay for) | Weeks 6–9 | ~35 hrs |
| **4** | Attendance + WhatsApp parent alerts | Weeks 10–12 | ~25 hrs |
| **5** | Connect student app to real backend (replace all mock data) | Weeks 13–16 | ~30 hrs |
| **6** | Polish, tests, performance tracker | Weeks 17–20 | ~25 hrs |

**Your pace:** ~10 hrs/week (2–3 hrs each weekend day + ~1 hr on weekdays)
**Projected completion:** ~October 2026

---

## PHASE 1 — Foundation (Weeks 1–3)

**What we're doing:** Rip out Firebase from the frontend, plug in Supabase instead, create the Owner model in the backend so a teacher can actually log in, and build the bare skeleton of the owner dashboard.

**Why this must come first:** Every other feature needs an authenticated owner. You can't build fee collection for "Sharma Classes" if Sharma sir can't log in. And Firebase + Supabase doing the same job is a bug waiting to happen — one auth source of truth.

---

### Task 1.1 — Backend: Add CORS + Owner model

**Why CORS:** Right now if you run the React app on `localhost:5173` and it tries to call the FastAPI backend on `localhost:8000`, the browser will block it with a CORS error. This one-line fix unblocks all frontend development.

**Why Owner model:** The `Student` model already exists for students. Owners are different — they have an institute name, a city, and they authenticate separately from students.

- [ ] **Add CORS to `app.py`**
  Open `BatchBook/app.py`. Import `CORSMiddleware` from `fastapi.middleware.cors` and add:
  ```python
  from fastapi.middleware.cors import CORSMiddleware
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["http://localhost:5173"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

- [ ] **Create `BatchBook/models/owner_base.py`**
  Mirror the pattern of `models/student_base.py`. The Owner table needs:
  `id` (int, PK), `name` (str), `phone_number` (str, unique), `user_id` (UUID string, unique — this links to Supabase Auth), `institute_name` (str, nullable for now), `city` (str, nullable), `created_at` (datetime)

- [ ] **Create Alembic migration**
  From the `BatchBook/` directory, run:
  ```bash
  alembic revision --autogenerate -m "add owner table"
  alembic upgrade head
  ```
  Then verify the table exists in your Supabase dashboard.

- [ ] **Create `BatchBook/repositories/owner_repository.py`**
  Copy the pattern from `repositories/student_repository.py`. You need four functions:
  `create_owner(db, owner_data)`, `get_by_user_id(db, user_id)`, `get_by_phone(db, phone)`, `update_owner(db, owner, updates)`

- [ ] **Create `BatchBook/services/owner_service.py`**
  Copy the OTP logic from `services/student_service.py`. The key methods:
  - `generate_otp(phone)` — calls Supabase to send SMS
  - `verify_otp(phone, token, name)` — verifies with Supabase, upserts owner record, returns JWT
  - `get_current_owner_id(supabase, authorization)` — validates JWT, returns user_id
  
  The `get_current_user_id` function in `student_service.py` can be extracted to a shared utility so you don't duplicate it. Put it in a new `services/auth_service.py`.

- [ ] **Create `BatchBook/routes/owner_route.py`** with 4 endpoints:
  - `POST /owner/generate_otp` — body: `{ phone: "9876543210" }`
  - `POST /owner/verify_otp` — body: `{ phone, token, name }`
  - `GET /owner/me` — requires `Authorization: Bearer <token>` header
  - `PATCH /owner/update` — body: `{ name, institute_name, city }` (all optional)

- [ ] **Register router in `app.py`**
  ```python
  from routes.owner_route import router as owner_router
  app.include_router(owner_router, prefix="/owner", tags=["owner"])
  ```

- [ ] **Smoke test:** Use the FastAPI `/docs` page (`http://localhost:8000/docs`) to send OTP to your phone and verify it. You should get back a JWT token.

---

### Task 1.2 — Backend: Institute model

**Why:** An owner has one institute (e.g., "Sharma Classes, Gurugram"). All batches, students, and fees are scoped to an institute. This is the top-level container for everything.

- [ ] **Create `BatchBook/models/institute_base.py`**
  Fields: `id` (int, PK), `owner_id` (FK → owner.id), `name` (str), `city` (str), `created_at` (datetime)

- [ ] **Create migration and run it**
  ```bash
  alembic revision --autogenerate -m "add institute table"
  alembic upgrade head
  ```

- [ ] **Create `BatchBook/repositories/institute_repository.py`**
  Functions: `create(db, data)`, `get_by_owner_id(db, owner_id)`, `update(db, institute, updates)`

- [ ] **Add 2 endpoints to `owner_route.py`**
  - `POST /owner/institute` — owner sets up their institute (name, city). Only allowed once per owner.
  - `GET /owner/institute` — get the owner's institute details.

---

### Task 1.3 — Frontend: Remove Firebase, add Supabase

**Why:** Firebase and Supabase are both doing phone OTP auth. They're completely separate systems. The backend only knows about Supabase JWTs — Firebase JWTs are useless to it. So the frontend must also use Supabase to generate tokens the backend will accept.

- [ ] **Remove Firebase**
  ```bash
  cd ~/WebstormProjects/batchbookui
  npm uninstall firebase
  ```
  Delete `src/firebaseconfig.ts`.

- [ ] **Install Supabase JS client**
  ```bash
  npm install @supabase/supabase-js
  ```

- [ ] **Create `src/lib/supabaseClient.js`**
  ```javascript
  import { createClient } from '@supabase/supabase-js'
  
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
  const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY
  
  export const supabase = createClient(supabaseUrl, supabaseAnonKey)
  ```
  Create a `.env` file in the project root with:
  ```
  VITE_SUPABASE_URL=https://wtckiivxgouyqweeieuc.supabase.co
  VITE_SUPABASE_ANON_KEY=<your anon key from backend .env>
  ```

- [ ] **Create `src/context/AuthContext.jsx`**
  This is the global auth state. Any component can call `useAuth()` to get the logged-in user and their JWT.
  ```jsx
  import { createContext, useContext, useEffect, useState } from 'react'
  import { supabase } from '../lib/supabaseClient'
  
  const AuthContext = createContext(null)
  
  export function AuthProvider({ children }) {
    const [session, setSession] = useState(null)
    const [loading, setLoading] = useState(true)
  
    useEffect(() => {
      supabase.auth.getSession().then(({ data: { session } }) => {
        setSession(session)
        setLoading(false)
      })
      const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
        setSession(session)
      })
      return () => subscription.unsubscribe()
    }, [])
  
    const signOut = () => supabase.auth.signOut()
  
    return (
      <AuthContext.Provider value={{ session, user: session?.user, loading, signOut }}>
        {children}
      </AuthContext.Provider>
    )
  }
  
  export const useAuth = () => useContext(AuthContext)
  ```

- [ ] **Rewrite `src/components/PhoneLogin.jsx`**
  Replace the Firebase `signInWithPhoneNumber` call with:
  ```javascript
  await supabase.auth.signInWithOtp({ phone: `+91${phoneNumber}` })
  ```
  Then navigate to `/otp-verification` passing the phone number via router state.

- [ ] **Rewrite `src/components/OtpVerification.jsx`**
  Replace Firebase `confirmationResult.confirm(otp)` with:
  ```javascript
  const { error } = await supabase.auth.verifyOtp({
    phone: `+91${phone}`,
    token: otp,
    type: 'sms'
  })
  ```
  On success, Supabase automatically sets the session (AuthContext picks it up). Navigate to dashboard.

- [ ] **Wrap `App.jsx` in `<AuthProvider>`**
  ```jsx
  import { AuthProvider } from './context/AuthContext'
  
  function App() {
    return (
      <AuthProvider>
        <Router> ... </Router>
      </AuthProvider>
    )
  }
  ```

- [ ] **Add protected route:** Any route under `/owner/*` or `/student/*` should redirect to `/phone-login` if there's no session.

---

### Task 1.4 — Frontend: Owner routes + basic dashboard shell

**Why:** The student dashboard already exists. We need a completely separate owner section with its own layout (sidebar navigation instead of bottom tabs, different pages entirely).

- [ ] **Create `src/services/api.js`** — the central axios instance
  ```javascript
  import axios from 'axios'
  import { supabase } from '../lib/supabaseClient'
  
  const api = axios.create({ baseURL: 'http://localhost:8000' })
  
  api.interceptors.request.use(async (config) => {
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`
    }
    return config
  })
  
  export default api
  ```
  This auto-attaches the Supabase JWT to every request. All `ownerService.js` and `dashboardService.js` calls use this instance.

- [ ] **Add owner routes to `App.jsx`**
  ```jsx
  <Route path="/owner/setup" element={<OwnerSetup />} />
  <Route path="/owner/dashboard" element={<OwnerDashboard />} />
  ```

- [ ] **Create `src/pages/owner/OwnerSetup.jsx`**
  A simple form: "Institute Name" + "City" text fields + Submit button.
  On submit: calls `POST /owner/institute` via api.js, then navigates to `/owner/dashboard`.
  This page only shows on first login (when owner has no institute set up yet).

- [ ] **Create `src/pages/owner/OwnerDashboard.jsx`**
  Placeholder layout with a left sidebar containing 4 nav links:
  - Students
  - Batches
  - Fees
  - Attendance
  
  The main content area just shows "Coming soon" for now. The sidebar is what matters — it's the shell everything else plugs into.

- [ ] **End-to-end test:** Open browser → go to `/phone-login` → enter your number → get OTP → verify → should land on `/owner/dashboard`. No Firebase errors, no CORS errors.

---

## PHASE 2 — Core Data Models (Weeks 4–5)

**What we're doing:** Create the Batch and Enrollment models, plus the frontend pages to manage them. This is the foundation — without batches, you can't collect fees or mark attendance.

**Why this before fees:** You can't charge fees for a batch that doesn't exist. You can't mark attendance for a session that isn't linked to a batch. The data model order matters.

---

### Task 2.1 — Backend: Batch model + CRUD APIs

**What a Batch is:** "Class 10 Maths — Monday/Wednesday/Friday 4–5 PM, max 30 students, ₹1500/month." Every coaching institute has multiple batches like this.

- [ ] **Create `BatchBook/models/batch_base.py`**
  Fields: `id`, `institute_id` (FK → institute.id), `name` (e.g. "Class 10 Maths"), `subject`, `grade` (nullable, e.g. "10"), `start_time` (Time), `end_time` (Time), `days_of_week` (JSON array, e.g. `["MON", "WED", "FRI"]`), `max_capacity` (int), `created_at`

- [ ] **Create migration and run it**

- [ ] **Create `BatchBook/repositories/batch_repository.py`**
  Functions: `create`, `get_all_by_institute_id`, `get_by_id`, `update`, `delete`

- [ ] **Create `BatchBook/services/batch_service.py`**
  Wraps the repo. Key responsibility: verify that the batch belongs to the requesting owner's institute before any operation (security check).

- [ ] **Create `BatchBook/routes/batch_route.py`** with 5 endpoints:
  - `POST /batch/` — create a new batch
  - `GET /batch/` — list all batches for this owner's institute
  - `GET /batch/{batch_id}` — get one batch
  - `PATCH /batch/{batch_id}` — update batch details
  - `DELETE /batch/{batch_id}` — delete batch (only if no active enrollments)

- [ ] Register router in `app.py`

---

### Task 2.2 — Backend: Enrollment model (student ↔ batch link)

**What Enrollment is:** When a student joins a batch, you create an Enrollment row. This is the pivot table between Student and Batch. Fee records and attendance records are attached to Enrollment, not directly to Student — because a student in 2 batches has 2 separate fee records and 2 attendance records.

- [ ] **Add `institute_id` (nullable FK) to StudentSchema** — so we know which institute a student belongs to. Create migration.

- [ ] **Create `BatchBook/models/enrollment_base.py`**
  Fields: `id`, `student_id` (FK → student.id), `batch_id` (FK → batch.id), `enrolled_at` (datetime), `is_active` (bool, default True)
  Unique constraint: `(student_id, batch_id)` — a student can't be enrolled in the same batch twice.

- [ ] **Create migration and run it**

- [ ] **Create `BatchBook/repositories/enrollment_repository.py`**
  Functions: `create`, `get_by_batch_id`, `get_by_student_id`, `get_active_by_batch_id`, `deactivate`

- [ ] **Create `BatchBook/routes/enrollment_route.py`** with 3 endpoints:
  - `POST /enrollment/` — enroll a student in a batch (body: `{ student_id, batch_id }`)
  - `GET /enrollment/batch/{batch_id}` — list all students in a batch
  - `DELETE /enrollment/{enrollment_id}` — remove student from batch (sets `is_active = False`)

- [ ] Register router in `app.py`

---

### Task 2.3 — Frontend: Batch management + Student list pages

- [ ] **Create `src/services/ownerService.js`**
  Functions that call `api.js`:
  - `getBatches()` → `GET /batch/`
  - `createBatch(data)` → `POST /batch/`
  - `getStudents()` → `GET /enrollment/batch/{batch_id}` (for each batch)
  - `addStudent(data)` → `POST /student/` then `POST /enrollment/`

- [ ] **Create `src/pages/owner/BatchesPage.jsx`**
  Shows a card for each batch: name, subject, timing (e.g. "Mon/Wed/Fri 4–5 PM"), enrolled count vs max capacity, an "Add Student" button per batch.
  Has a "New Batch" button at the top.

- [ ] **Create `src/pages/owner/CreateBatchModal.jsx`**
  MUI Dialog. Form fields: Batch Name, Subject, Grade (optional), Start Time, End Time, Days (multi-select checkboxes), Max Capacity. Submit → calls `createBatch()` → closes modal → refreshes batch list.

- [ ] **Create `src/pages/owner/StudentsPage.jsx`**
  Table: student name, phone number, which batch(es) they're in, fee status.
  Search by name. "Add Student" button.

- [ ] **Create `src/pages/owner/AddStudentModal.jsx`**
  Form: Name, Phone Number, select Batch. Submit → `addStudent()` → success toast.

- [ ] **Wire pages into `OwnerDashboard.jsx`** sidebar navigation

---

## PHASE 3 — Fee Management MVP (Weeks 6–9)

**What we're doing:** The core product. An owner can set a monthly fee per batch, see who has and hasn't paid for a given month, send WhatsApp reminders to defaulters, mark cash/UPI payments, and generate receipts.

**Why this is the MVP:** This is the one thing institute owners will pay ₹699/month for. "I saved 8 hours this month not chasing parents on WhatsApp" is the exact moment they become paying customers.

---

### Task 3.1 — Backend: FeeStructure + FeeRecord models

**FeeStructure:** The fee config for a batch. "Class 10 Maths charges ₹1500/month due on the 5th." One FeeStructure per Batch.

**FeeRecord:** One record per student per month. "Rahul (Enrollment #47) owes ₹1500 for May 2026. Status: NOT_PAID." When Rahul pays, this record gets updated.

- [ ] **Create `BatchBook/models/fee_structure_base.py`**
  Fields: `id`, `batch_id` (FK, unique — one structure per batch), `monthly_amount` (Numeric/Decimal), `due_day` (int, 1–28), `created_at`

- [ ] **Create `BatchBook/models/fee_record_base.py`**
  Fields: `id`, `enrollment_id` (FK → enrollment.id), `month` (Date — stored as first day of month, e.g. 2026-05-01), `amount_due` (Numeric), `amount_paid` (Numeric, default 0), `status` (Enum: NOT_PAID / PARTIALLY_PAID / FULLY_PAID, default NOT_PAID), `paid_at` (datetime, nullable), `payment_reference` (str, nullable — UPI transaction ID), `payment_link` (str, nullable — Razorpay link URL), `created_at`
  Unique constraint: `(enrollment_id, month)` — one record per student per month

- [ ] **Create migrations and run them**

- [ ] **Create `BatchBook/repositories/fee_repository.py`**
  Functions:
  - `create_or_update_structure(db, batch_id, amount, due_day)`
  - `get_structure_by_batch(db, batch_id)`
  - `bulk_create_records(db, records_list)` — create many FeeRecord rows at once
  - `get_records_by_batch_and_month(db, batch_id, month)` — for the fee dashboard
  - `get_record_by_id(db, record_id)`
  - `update_payment(db, record_id, amount_paid, reference)` — updates amount_paid, status, paid_at

- [ ] **Create `BatchBook/services/fee_service.py`**
  Key methods:
  - `setup_fee_structure(batch_id, amount, due_day)` — creates or overwrites the FeeStructure for a batch
  - `generate_monthly_records(batch_id, month_str)` — takes all **active** enrollments in the batch, creates one FeeRecord per enrollment for that month (amount_due = FeeStructure.monthly_amount). Skip if record already exists (idempotent).
  - `mark_payment(record_id, amount_paid, reference)` — updates the record. If amount_paid >= amount_due → status = FULLY_PAID. If 0 < amount_paid < amount_due → PARTIALLY_PAID.
  - `get_fee_dashboard(institute_id, month_str)` — returns: total_due (sum), total_collected (sum), total_pending (sum), collection_rate (%), list of all records with student name + batch name

---

### Task 3.2 — Backend: Fee API routes

- [ ] **Create `BatchBook/routes/fee_route.py`** with these endpoints:
  - `POST /fee/structure` — body: `{ batch_id, monthly_amount, due_day }` — set fee for a batch
  - `POST /fee/generate/{batch_id}?month=2026-05` — generate fee records for a month
  - `PATCH /fee/record/{record_id}/pay` — body: `{ amount_paid, reference }` — mark payment
  - `GET /fee/dashboard?month=2026-05` — institute-wide fee summary
  - `GET /fee/batch/{batch_id}?month=2026-05` — fee status list for one batch

- [ ] Register router in `app.py`

---

### Task 3.3 — Backend: Razorpay UPI payment links

**Why:** Instead of telling parents "please pay to UPI ID xyz@bank", you generate a Razorpay payment link with the exact amount pre-filled. Parent clicks the link, pays, done. You don't chase them.

- [ ] **Sign up for Razorpay** at razorpay.com → Dashboard → Settings → API Keys → generate test key
  Add to `BatchBook/.env`:
  ```
  RAZORPAY_KEY_ID=rzp_test_xxxxx
  RAZORPAY_KEY_SECRET=xxxxxxxx
  ```

- [ ] **Add razorpay to `pyproject.toml`** and install: `pip install razorpay`

- [ ] **Create `BatchBook/clients/razorpay_client.py`**
  ```python
  import razorpay
  from config import settings
  
  client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
  
  def create_payment_link(amount_rupees: float, description: str, student_name: str) -> str:
      link = client.payment_link.create({
          "amount": int(amount_rupees * 100),  # Razorpay uses paise
          "currency": "INR",
          "description": description,
          "customer": { "name": student_name },
          "notify": { "sms": False, "email": False },
      })
      return link["short_url"]
  ```

- [ ] **Add `GET /fee/record/{record_id}/payment-link` endpoint** — generates Razorpay link, saves it to `FeeRecord.payment_link`, returns it

---

### Task 3.4 — Backend: WhatsApp fee reminders via WATI

**Why:** The whole point. Instead of the owner manually texting each parent "Please pay ₹1500 for May", the owner clicks one button and WATI sends templated WhatsApp messages to all defaulters automatically.

- [ ] **Sign up for WATI** at wati.io → get API endpoint URL + API token → add to `.env`:
  ```
  WATI_API_ENDPOINT=https://live-mt-server.wati.io/XXXXX
  WATI_API_TOKEN=xxxxxxxx
  ```

- [ ] **Create WhatsApp message templates in WATI dashboard** (takes 24hrs for WhatsApp approval):
  - Template `fee_reminder`: "Hi {{1}}, your fee of ₹{{2}} for {{3}} is due on {{4}}. Pay here: {{5}}"
  - Template `fee_receipt`: "Hi {{1}}, payment of ₹{{2}} received for {{3}} on {{4}}. Thank you!"

- [ ] **Create `BatchBook/clients/wati_client.py`**
  ```python
  import httpx
  from config import settings
  
  async def send_template_message(phone: str, template_name: str, params: list[str]):
      async with httpx.AsyncClient() as client:
          response = await client.post(
              f"{settings.WATI_API_ENDPOINT}/api/v1/sendTemplateMessage",
              headers={"Authorization": f"Bearer {settings.WATI_API_TOKEN}"},
              json={
                  "template_name": template_name,
                  "broadcast_name": template_name,
                  "parameters": [{"name": str(i+1), "value": v} for i, v in enumerate(params)],
                  "receivers": [{"whatsappNumber": f"91{phone}"}],
              }
          )
      return response.json()
  ```

- [ ] **Create `BatchBook/services/notification_service.py`**
  - `send_fee_reminder(fee_record_id)` — fetches record + student + batch → calls WATI `fee_reminder` template
  - `send_fee_receipt(fee_record_id)` — called automatically after `mark_payment` → sends receipt

- [ ] **Add reminder endpoints to `fee_route.py`**:
  - `POST /fee/remind/{record_id}` — remind one student
  - `POST /fee/remind-all?batch_id=X&month=2026-05` — remind all NOT_PAID students in a batch

- [ ] **Auto-send receipt:** In `fee_service.mark_payment()`, after updating the record, call `notification_service.send_fee_receipt(record_id)` asynchronously.

---

### Task 3.5 — Frontend: Fee Management pages

- [ ] **Add fee functions to `src/services/ownerService.js`**:
  `getFeeDashboard(month)`, `getBatchFees(batchId, month)`, `setupFeeStructure(batchId, amount, dueDay)`, `generateMonthlyRecords(batchId, month)`, `markPayment(recordId, amountPaid, reference)`, `sendReminder(recordId)`, `sendBulkReminder(batchId, month)`, `getPaymentLink(recordId)`

- [ ] **Create `src/pages/owner/FeesPage.jsx`**
  Layout:
  - Top: Month selector (MUI DatePicker, months only)
  - Below: 4 summary cards — "Total Due", "Collected", "Pending", "Collection %"
  - Below: Tabs for each batch
  - In each batch tab: table of students with columns — Name, Amount Due, Amount Paid, Status chip (green/yellow/red), [Remind] button, [Mark Paid] button, [Copy UPI Link] icon

- [ ] **Create `src/pages/owner/FeeSetupModal.jsx`**
  MUI Dialog. Fields: Monthly Amount (number input), Due Day (1–28). Submit → `setupFeeStructure()` → then `generateMonthlyRecords()` for current month.

- [ ] **Create `src/pages/owner/MarkPaymentModal.jsx`**
  MUI Dialog. Fields: Amount Paid (prefilled with full amount), Transaction Reference (UPI ID or "Cash"). Submit → `markPayment()` → row updates to green.

- [ ] **Smoke test (the real one):** Set up fee ₹1500 for a batch → generate records → see a student as NOT_PAID → click Remind → parent receives WhatsApp → click Mark Paid → status turns green → parent receives receipt WhatsApp.

---

## PHASE 4 — Attendance + WhatsApp Parent Alerts (Weeks 10–12)

**What we're doing:** Teacher clicks "Start Session" → sees list of all students → marks each present/absent → clicks Submit → parents of absent students get an automatic WhatsApp.

**Why this matters:** Attendance disputes are one of the biggest sources of parent-teacher friction. An automatic WhatsApp ("Rahul was absent today") prevents disputes and builds trust.

---

### Task 4.1 — Backend: ClassSession + Attendance models

**ClassSession:** One row per class held. "Batch: Class 10 Maths, Date: 2026-05-05, Time: 4–5 PM."

**Attendance:** One row per student per session. "Rahul, Session #34: PRESENT."

- [ ] **Create `BatchBook/models/class_session_base.py`**
  Fields: `id`, `batch_id` (FK), `date` (Date), `start_time`, `end_time`, `topic` (nullable), `created_at`

- [ ] **Create `BatchBook/models/attendance_base.py`**
  Fields: `id`, `session_id` (FK → class_session.id), `enrollment_id` (FK → enrollment.id), `status` (Enum: PRESENT / ABSENT / LATE, default ABSENT), `marked_at` (datetime)
  Unique constraint: `(session_id, enrollment_id)`

- [ ] **Create migrations and run them**

- [ ] **Create `BatchBook/services/attendance_service.py`**
  Key methods:
  - `create_session(batch_id, date)` — creates a ClassSession, then pre-creates one Attendance row per active enrollment with status=ABSENT (so you don't have to handle "missing = absent" later)
  - `bulk_mark(session_id, present_enrollment_ids)` — sets all provided IDs to PRESENT; all others stay ABSENT. After this, for every ABSENT enrollment → call `notification_service.send_absence_alert(enrollment_id, date)` async
  - `get_session_attendance(session_id)` — returns all attendance rows + student names
  - `get_student_attendance_summary(enrollment_id, month_str)` — returns `{ present: 18, total: 22, percentage: 81.8 }`

---

### Task 4.2 — Backend: Absence WhatsApp alert

- [ ] **Add to `BatchBook/services/notification_service.py`**:
  - Create WATI template `absence_alert` in WATI dashboard: "Hi, {{1}} was absent from {{2}} today ({{3}}). Please contact us if this is unexpected."
  - `send_absence_alert(enrollment_id, date)` — fetch student + batch, call WATI template

---

### Task 4.3 — Backend: Attendance routes

- [ ] **Create `BatchBook/routes/attendance_route.py`**:
  - `POST /attendance/session` — create session (body: `{ batch_id, date }`)
  - `POST /attendance/session/{session_id}/mark` — body: `{ present_enrollment_ids: [1, 3, 5] }`
  - `GET /attendance/session/{session_id}` — get full attendance for a session
  - `GET /attendance/batch/{batch_id}?month=2026-05` — monthly summary for all students in batch
  - `GET /attendance/student/{enrollment_id}?month=2026-05` — one student's monthly summary

- [ ] Register router in `app.py`

---

### Task 4.4 — Frontend: Attendance pages

- [ ] **Create `src/pages/owner/AttendancePage.jsx`**
  - Date picker + Batch selector at the top
  - If a session exists for that date + batch: show the attendance sheet for it
  - If no session: show "Start Session" button → on click, calls `POST /attendance/session` → loads student list
  - Below: monthly attendance summary table (student name | present days | total days | %)

- [ ] **Create `src/pages/owner/MarkAttendanceSheet.jsx`**
  - Lists all students in the batch
  - Each student: large toggle button PRESENT (green) / ABSENT (red) — default all PRESENT
  - "Submit Attendance" button → calls bulk mark → shows success toast "Absence alerts sent to X parents"

---

## PHASE 5 — Connect Student App to Real Backend (Weeks 13–16)

**What we're doing:** All the mock data in the student-facing dashboard gets replaced with real API calls. Rahul logs in and sees his actual 18/22 attendance, his actual ₹1500 fee status, and tomorrow's actual session.

---

### Task 5.1 — Backend: Student-facing read APIs

These are read-only endpoints for students to view their own data.

- [ ] **Create `BatchBook/routes/student_dashboard_route.py`**:
  - `GET /student/me/attendance?month=2026-05` — student's attendance summary for the month (uses enrollment_id from their student record)
  - `GET /student/me/fee?month=2026-05` — student's fee record for the month (status, amount, payment link)
  - `GET /student/me/schedule?date=2026-05-05` — all class sessions across all their batches for a given date
  - `GET /student/me/upcoming-events?limit=10` — next N sessions across all their batches

- [ ] Register router in `app.py`

---

### Task 5.2 — Frontend: Replace mock data in student dashboard

- [ ] **Rewrite `src/services/dashboardService.js`**
  Replace every mock `setTimeout` / hardcoded return with real `api.js` calls:
  - `getStudentProfile()` → `GET /student/me`
  - `getAttendance(month)` → `GET /student/me/attendance?month=...`
  - `getFeeStatus(month)` → `GET /student/me/fee?month=...`
  - `getTodaySchedule()` → `GET /student/me/schedule?date=today`
  - `getUpcomingEvents()` → `GET /student/me/upcoming-events`

- [ ] **Update `src/components/Dashboard.jsx`**
  Handle loading states (show skeleton/spinner while fetching).
  Handle errors (show "Could not load data" with retry button).
  Fee alert banner: if fee status is NOT_PAID → show banner with real amount and real Razorpay payment link.

- [ ] **End-to-end test:** Student logs in via phone OTP → sees real attendance (e.g. 18/22) → Schedule tab shows real sessions → Profile shows real name from backend.

---

## PHASE 6 — Polish, Tests & Performance Tracker (Weeks 17–20)

**What we're doing:** Add tests so we can refactor with confidence, add the performance tracker (a V2 upsell feature), and add proper error handling everywhere.

---

### Task 6.1 — Backend: Tests

**Why tests now:** The core features are stable. Now we need a safety net before we start optimizing and adding analytics logic.

- [ ] **Set up pytest with async support**
  Add to `pyproject.toml`: `pytest-asyncio`, `httpx` (for TestClient), `aiosqlite` (for in-memory test DB)

- [ ] **Create `tests/conftest.py`** with fixtures:
  - `test_db` fixture: creates an in-memory SQLite async session for each test
  - `client` fixture: FastAPI TestClient with the test DB injected via dependency override

- [ ] **Write `tests/test_fee_service.py`**:
  - Test: `generate_monthly_records` for a batch with 3 students creates exactly 3 FeeRecord rows with correct amounts
  - Test: `mark_payment` with full amount sets status to FULLY_PAID
  - Test: `mark_payment` with partial amount sets status to PARTIALLY_PAID

- [ ] **Write `tests/test_attendance_service.py`**:
  - Test: `create_session` creates N attendance rows (one per active enrollment) all with ABSENT status
  - Test: `bulk_mark` with IDs [1, 3] marks those as PRESENT and leaves others ABSENT

- [ ] **Write `tests/test_auth.py`**:
  - Test: `GET /owner/me` without token returns 401
  - Test: `GET /owner/me` with invalid token returns 401

- [ ] Run: `pytest -v` — all tests should pass

---

### Task 6.2 — Backend: Performance tracker

**Why:** This is the upsell to the Pro plan (₹1499/month). Owners can enter test scores, students can see their score trends, and the system auto-flags students who are declining.

- [ ] **Create `BatchBook/models/test_score_base.py`**
  Fields: `id`, `enrollment_id` (FK), `test_name`, `subject`, `date`, `max_marks` (int), `obtained_marks` (int), `created_at`

- [ ] **Create migration + repo + service**

- [ ] **Create endpoints**:
  - `POST /scores/` — enter test score (owner only)
  - `GET /scores/student/{enrollment_id}` — get all scores for a student. Include `needs_attention: true` in response if the average of last 3 scores < 60% of max marks.

---

### Task 6.3 — Frontend: Performance tab + analytics

- [ ] Add "Tests" to owner sidebar
- [ ] Create score entry form (student selector, test name, subject, max marks, obtained marks)
- [ ] Create student report card: last 3 test scores, attendance %, `needs_attention` badge in red if flagged
- [ ] Add to `OwnerDashboard.jsx` header: "X students enrolled | ₹Y collected this month | Z% avg attendance"

---

### Task 6.4 — Error handling & stability

- [ ] **Backend: Global exception handler in `app.py`**
  ```python
  @app.exception_handler(Exception)
  async def global_exception_handler(request, exc):
      return JSONResponse(status_code=500, content={"detail": "Internal server error"})
  ```

- [ ] **Backend: Request logging middleware** — log method, path, status code, response time on every request

- [ ] **Frontend: Error boundary** — wrap each page in a React error boundary that shows a "Something went wrong" screen instead of a blank white page

- [ ] **Frontend: Global error toast** — if any `api.js` call fails with a non-401 error, show a MUI Snackbar "Failed to load data. Please try again."

---

## External Services Setup Checklist

These need to be set up before Phase 3. Don't leave them to the last minute — WATI template approval can take 24–48 hrs.

- [ ] **Supabase:** Already configured. Get anon key from Supabase dashboard → Settings → API for the frontend `.env`
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
RAZORPAY_KEY_ID=rzp_test_xxxxx          # Add in Phase 3
RAZORPAY_KEY_SECRET=xxxxxxxx             # Add in Phase 3
WATI_API_ENDPOINT=https://live-mt-server.wati.io/XXXXX  # Add in Phase 3
WATI_API_TOKEN=xxxxxxxx                  # Add in Phase 3
```

**Frontend `batchbookui/.env`:**
```
VITE_SUPABASE_URL=https://[project-id].supabase.co   # Add in Phase 1
VITE_SUPABASE_ANON_KEY=eyJhbGci...                   # Add in Phase 1
```

---

## How to Run the Projects

**Backend:**
```bash
cd ~/PycharmProjects/BatchBook
source .venv/bin/activate   # or however your venv is named
uvicorn app:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

**Frontend:**
```bash
cd ~/WebstormProjects/batchbookui
npm run dev
# App: http://localhost:5173
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
