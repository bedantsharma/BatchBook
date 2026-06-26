# Student Onboarding + Verification-Gated Notification Audit — Design

**Date:** 2026-06-26
**Issues:** BatchBook #38, batchbookui #34 (onboarding loopholes), BatchBook #36 (data corruption)
**Repos affected:** `BatchBook` (backend), `batchbookui` (frontend submodule)

---

## 1. Problem

Two GitHub issues, three filings, one shared root cause.

### Root cause
The frontend "Add Student" modal and the self-onboarding wizard bypass the correct,
already-built backend endpoints:

- **AddStudentModal → `addStudentAndEnroll()`** (`batchbookui/src/services/ownerService.js`)
  calls `POST /student/` then `POST /enrollment/`.
  - `POST /student/` uses the `Student` DTO, which has **no `phone_number` field** — the
    entered phone is silently dropped, and **no Parent record is created**. The student is
    born with `parent_id = NULL`, `institute_id = NULL`.
  - `POST /enrollment/` only auto-assigns `institute_id`; `parent_id` stays `NULL` forever →
    **orphan student** (issue #36, point 2).
- The backend **already has** the correct endpoint `POST /enrollment/invite` →
  `EnrollmentService.invite_student()`, which creates Parent + Student + Enrollment in one
  transaction, links them to the institute, and fires the `enrollment_invite` WhatsApp
  template. **The frontend never calls it**, and the modal never collects a parent name.
- **Self-onboarding wizard** (`OnboardingWizard.jsx` → `PhoneOtpStep.jsx`): `verifyOtp()`
  POSTs only `{ phone, token }` to `/parent/verify_otp` — the collected `parentName` is never
  sent (issue #36, point 1) — and even if it were, `ParentService.get_or_create_after_otp()`
  does not update `name` on an existing parent.

### What the issues ask for
- **#36 (data corruption):** every student must have a name and a `parent_id`; every parent
  must have a name and an OTP-verified phone. No orphan students.
- **#38 (loophole):** owner adds a student → parent receives a WhatsApp `enrollment_invite`
  with a prefilled onboarding link → parent OTP-verifies their own phone → details saved
  end-to-end.

---

## 2. Requirements (confirmed with user)

1. Every student has a name and a `parent_id` (no orphans).
2. Every parent has a name.
3. Every parent's phone is OTP-verified (Supabase + Twilio; OTP yields the auth token).
4. Owner adds a student up front; Parent + Student + Enrollment are **created immediately**
   so the student is visible to the owner (attendance/fees) right away. The parent verifies
   their phone later via the invite link.
5. **Verification gate on outbound messaging:** before sending any parent-facing reminder
   (fee/absence), check if the parent's number is verified. If **not** verified, send the
   onboarding/invite link instead, mark that reminder as not-sent with reason
   "parent number not verified", surface it to the owner on the dashboard, and persist the
   reason.
6. **Every notification send is audited** in a notifications table — fee_reminder,
   fee_receipt, absence_alert, enrollment_invite, verified or not. Each row stores the
   message body, institute_id, and the raw WhatsApp API response (in a JSON `metadata`
   column) for later delivery verification.

---

## 3. Core decisions

- **"Verified" is derived from `Parent.user_id IS NOT NULL`.** No new boolean column.
  A parent's `user_id` is set only when they complete Supabase OTP. Owner-created parents
  are **stubs**: `phone_number` + `name`, `user_id = NULL`.
- **All add-student traffic goes through `POST /enrollment/invite`.** `POST /student/`
  remains for admin/internal use but is no longer the frontend's path.
- **Audit log lives in a new `Notification` table** (table name `notifications`).

---

## 4. Backend changes (`BatchBook`)

### 4.1 Data-integrity fix — `ParentService.get_or_create_after_otp`
Currently looks up only by `user_id`. New resolution order:

1. Look up by `user_id`. If found, return (optionally backfill `name` if missing and a name
   was supplied).
2. Else look up by **phone**. If a stub exists (owner-created, `user_id = NULL`), **attach
   `user_id`** and set `name` (if provided or currently missing), then save. This is the
   "claim" step that links the invite to the OTP login.
3. Else create a new parent with `user_id`, `phone`, `name`.

This single fix: (a) persists the parent name, (b) links invite → OTP login, (c) prevents the
`phone_number` UNIQUE violation that would otherwise occur when a stub parent logs in.

### 4.2 New model — `models/notification_base.py`
```
NotificationSchema  (__tablename__ = "Notification")
  id            Integer PK
  parent_id     Integer FK -> Parent.id        (nullable; some sends may precede parent row)
  student_id    Integer FK -> Student.id        (nullable)
  institute_id  Integer FK -> Institute.id      (indexed; for owner dashboard queries)
  type          Enum: fee_reminder | fee_receipt | absence | enrollment_invite
  status        Enum: sent | skipped_unverified | failed
  reason        String (nullable)               e.g. "parent number not verified"
  meta_data     JSON                            { message, institute_id, whatsapp_response }
  created_at    DateTime
```
Registered in `models/__init__.py`; one Alembic autogenerate migration. (Column attribute is
named `meta_data` to avoid SQLAlchemy's reserved `metadata`; the issue's intent — message +
institute_id + WhatsApp response — is stored inside it.)

`NotificationRepository` (create + query latest-per-student-by-institute) and a
`NotificationType` / `NotificationStatus` enum module.

### 4.3 Gated + audited orchestration — `notification_service`
A single orchestration entry point wraps **all** sends:

```
async def dispatch(db, *, parent, student, institute_id, type, build_components, send_fn,
                   join_url) -> NotificationSchema
```
Behavior:
- If `parent.user_id` is set (verified): call `send_fn` (the existing template wrapper),
  capture the WhatsApp API response, write a `Notification` row with status `sent`
  (response in `meta_data`). On exception → status `failed`, reason = error string.
- If `parent.user_id` is None (unverified) **and** the message is a parent-facing reminder
  (fee/absence): send `enrollment_invite` (the onboarding link) instead, write a
  `Notification` row with status `skipped_unverified`, reason `"parent number not verified"`,
  and the invite send's response in `meta_data`.
- `enrollment_invite` itself is always logged (status `sent`/`failed`).

The existing `send_fee_reminder` / `send_fee_receipt` / `send_absence_alert` /
`send_enrollment_invite` template wrappers in `notification_service.py` remain as the
low-level senders; `dispatch` calls them and the WhatsApp client returns its response body so
it can be logged. Background tasks open their own session via `AsyncSessionLocal` (the
request-scoped session is gone by the time the background task runs).

### 4.4 Wire reminder endpoints through `dispatch`
- `POST /fee/{record_id}/remind` and `POST /fee/remind-all` (`routes/fee_route.py`): fetch the
  parent (already joined), pass through `dispatch` instead of calling `send_fee_reminder`
  directly. Records get audited; unverified parents get an invite + skipped log.
- Payment receipt send (`routes/fee_route.py` `mark_payment`) and absence alerts
  (attendance route) route through `dispatch` too, for full audit coverage.

### 4.5 Surface status to the owner
- Add `parent_is_verified: bool` and `last_notification_status` / `last_notification_reason`
  to the fee dashboard response (`routes/responses/fee_dashboard_response.py`), sourced from
  the latest `Notification` row per student. This lets the dashboard show
  "⚠ Parent not verified — invite re-sent". (No separate notifications endpoint for now;
  revisit if the dashboard needs full history.)

---

## 5. Frontend changes (`batchbookui`)

### 5.1 `AddStudentModal.jsx`
- Add a **Parent Name** field (required).
- Relabel "Phone Number" → **Parent's phone**.
- Switch the submit handler from `addStudentAndEnroll()` to a call against
  `POST /enrollment/invite` with `{ student_name, parent_name, parent_phone, batch_id,
  due_day, first_month_amount }`.

### 5.2 `ownerService.js`
- Add `inviteStudent(payload)` → `POST /enrollment/invite`.
- Mark `addStudentAndEnroll()` deprecated (kept only if still referenced elsewhere;
  otherwise removed).

### 5.3 Invite-link landing — new `/join/:joinCode` route
- New route in `App.jsx` + component that reads the optional `?student=<name>` query param,
  prefills the student name (display only), and runs the parent OTP step.
- OTP verification calls `/parent/verify_otp`; the by-phone claim in §4.1 links the parent to
  the stub the owner created, so the parent immediately sees their child.
- The backend invite URL (`enrollment_route.py`) is updated to include the student name as a
  query param: `https://batchbook.in/join/{join_code}?student={student_name}`.

### 5.4 Self-onboarding `PhoneOtpStep.jsx`
- Pass `name: parentName` in the `/parent/verify_otp` body so the parent name persists.

### 5.5 Owner dashboard surfacing
- `StudentsPage.jsx` / `FeesPage.jsx`: render an "unverified — invite re-sent / reminder
  skipped" badge using `parent_is_verified` / `last_notification_status` from the fee
  dashboard response.

---

## 6. Testing

### Backend (pytest)
- `get_or_create_after_otp`: (a) claims an existing stub by phone, attaches `user_id`,
  persists name; (b) backfills name on existing verified parent; (c) creates fresh parent.
- `POST /enrollment/invite`: creates Parent + Student + Enrollment all linked to the
  institute; no orphan student possible.
- `dispatch`: verified → `sent` row with WhatsApp response in `meta_data`; unverified →
  `enrollment_invite` sent + `skipped_unverified` row with reason; send error → `failed` row.
- Fee reminder endpoints write `Notification` audit rows.

### Frontend (vitest)
- `AddStudentModal` sends `parent_name` + `parent_phone` to the invite endpoint (not the old
  `/student/` path).
- `/join/:joinCode` route prefills the student name from the query param and verifies OTP.

---

## 7. Delivery

- **Backend:** branch off `master`, PR. Includes the Alembic migration.
- **Frontend:** committed inside the `batchbookui` submodule on its own branch + PR (per the
  submodule rules in CLAUDE.md), followed by a pointer bump in `BatchBook`.

---

## 8. Out of scope

- Razorpay button-CTA template change (existing TODO).
- Local JWT verification to replace the Supabase `get_user()` round-trip (existing TODO).
- A full notifications history endpoint/UI (only latest-status surfacing for now).
- Generic (non-invited) self-signup creating students without an institute — invited parents
  are the supported path; the wizard only persists the parent name fix.
