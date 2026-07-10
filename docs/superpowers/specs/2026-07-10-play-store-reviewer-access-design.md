# Play Store Reviewer Access — Design

**Date:** 2026-07-10
**Trigger:** Google Play review requirement — reviewers must be able to sign in and reach every
part of the app without creating a real account, using a personal number, or a free trial.
**Repos affected:** `BatchBook` (backend), `BATCHBOOK_APP` (React Native, sibling repo — the app
being submitted to Play Store). `batchbookui` (web frontend submodule) needs no changes.

---

## 1. Problem

Google's reviewers need a working Owner login and a working Student login inside
`BATCHBOOK_APP`, pre-populated with enough real-looking data (institute, batches, attendance,
fees) that every screen renders meaningfully. Two things stand in the way today:

1. **No reviewer-accessible test accounts.** All login is real OTP-based Supabase phone auth —
   there was no way to grant a reviewer a working session without a live phone number.
2. **The RN app's student login path is a dead end.** Picking "I'm a Student" in
   `(auth)/onboarding.tsx` shows a static "ask your tutor for a link" card and never calls the
   OTP endpoints. Only the Owner flow (`phone-login.tsx` → `otp-verification.tsx`) is wired up.

### What was ruled out

- **A custom backend bypass** (whitelist phone numbers, skip Supabase verification) was
  considered and rejected: `services/auth_service.py` validates every JWT against Supabase's
  real JWKS signature (ES256, `jwt.decode(..., algorithms=["ES256"], audience="authenticated")`).
  A fabricated token would fail that check, and weakening it to accommodate one would open a
  second, permanent auth path in production for no good reason.
- **Supabase Admin API session minting** was considered and rejected: `admin.generate_link`
  only supports email-based flows (magiclink/signup/recovery/invite), not phone/SMS sessions —
  there's no admin endpoint that mints a phone-auth session directly.

### What's actually used instead

Supabase's hosted dashboard has a **Test OTP** feature (Auth → Providers → Phone → Test OTP)
built specifically for this scenario (app-store reviewers, CI, local dev). The project owner has
already configured it in the production Supabase project (`wtckiivxgouyqweeieuc`):

| Role  | Phone         | OTP      | Valid until      |
|-------|---------------|----------|-------------------|
| Owner | `9999999999`  | `110304` | 2026-08-31        |
| Student (Parent) | `9999999998` | `110304` | 2026-08-31 |

Verified end-to-end against the live project on 2026-07-10 (`POST /auth/v1/otp` then
`POST /auth/v1/verify` against `wtckiivxgouyqweeieuc.supabase.co` returned a genuine
`access_token`/`refresh_token` pair). **This makes the entire "how do we bypass JWT auth"
question moot — these numbers get real, fully valid Supabase sessions through the app's existing,
unmodified `sign_in_with_otp` / `verify_otp` calls.** No backend auth code, JWT validation, or
frontend auth-bridging logic changes.

The one config gotcha (already hit and fixed during this investigation): Supabase's Test OTP
phone-number match is against GoTrue's normalized form — digits + country code, no `+`, no
spaces (e.g. `919999999999`) — not the raw 10-digit or `+`-prefixed forms. A mismatch there is
why phone auth silently falls through to the real Twilio Verify provider (observed as
`"twilio verification error: pending"` / `otp_expired` in the project's auth logs) instead of
being intercepted.

**What's actually missing, then, is data and one screen:**
- The Owner/Student test accounts have no seeded Institute/Batches/Student/Attendance/Fees —
  reviewers would land on an empty app.
- The RN Student login screens don't exist yet.

---

## 2. Requirements (confirmed with user)

1. Reviewers can log in as an Owner (`9999999999`) and see a populated institute: batches with
   schedules, a roster, attendance history, fee records (mix of paid/due) — a "rich single
   institute," not a bare empty shell.
2. Reviewers can log in as a Student (`9999999998`), enrolled in that same institute, and see
   their own schedule/attendance/fee status populated to match.
3. Both logins must work in **`BATCHBOOK_APP`** (the app actually submitted to Play Store) —
   Owner already works there; Student does not yet and must be built.
4. Seeding must be **idempotent and re-triggerable** — Google may re-review after a future
   update, and Test OTP data can drift or get modified by a reviewer poking around the app. No
   one should need prod DB shell access to reset it.
5. The demo data must be created the way the app *actually* onboards a parent+student in
   production (see §3) — not a shortcut that only coincidentally looks similar.
6. No changes to Supabase auth config, JWT validation, or any existing login code path for real
   users.

---

## 3. The real owner→parent onboarding flow (why the seed can't use `join_code`)

Investigated directly in the codebase because the initial assumption (parents self-join via
`Institute.join_code`) turned out to be wrong for the primary path:

- The owner clicks **"Add Student"** in the dashboard → `POST /enrollment/invite`
  (`routes/enrollment_route.py`) → `EnrollmentService.invite_student()`
  (`services/enrollment_service.py:146-194`), which in one transaction:
  1. Finds or creates a **Parent stub**: `phone_number` + `institute_id` set, **`user_id = NULL`**.
  2. Creates a **Student**: `name`, `parent_id`, `institute_id`.
  3. Creates an **Enrollment** linking the student to a batch.
  4. Fires a WhatsApp message (Meta Graph API, `enrollment_invite` template) containing
     `https://batchbook.in/join/{join_code}?student={name}`.
- The parent clicks that link, lands on `JoinInstitute.jsx`, and enters **their own phone
  number** — the `join_code` in the URL is read only for cosmetic display and is **never
  validated** by the frontend or by `verify_otp`.
- On real OTP verify, `ParentService.get_or_create_after_otp()`
  (`services/parent_service.py:16-40`) looks the parent up **by phone number**, finds the
  owner-created stub, and attaches the real Supabase `user_id` to it. That phone match — not the
  join code — is what actually links a verifying parent to the right institute/student.

**Conclusion for seeding:** the demo Parent/Student rows must be created in the same
stub shape (`Parent.user_id = NULL`, `institute_id` set; `Student.parent_id` + `institute_id`
set) that `invite_student` produces, so that when `9999999998` completes Test-OTP verification,
the existing phone-match logic claims the pre-seeded stub exactly as it would for a real parent —
no special-casing needed in `parent_service.py`.

---

## 4. Backend changes (`BatchBook`)

### 4.1 New endpoint — `POST /admin/seed-demo-accounts`

Added to `routes/admin_route.py`, reusing the existing `_verify_admin_secret` dependency
(`X-Admin-Secret` header, `hmac.compare_digest` against `ADMIN_BACKFILL_SECRET`) — the same
pattern as `backfill-payment-links` and `institute/{id}/generate-site`.

Idempotent upsert logic, keyed on `phone_number` (never on Supabase UUID — that field is only
populated on first real login, same as any other owner/parent):

1. **Owner** — `phone_number = "9999999999"`. Create if absent (placeholder `teacher_id`, real
   one gets attached on first login via the existing phone-fallback in
   `owner_service.get_or_create_after_otp`).
2. **Institute** — owned by that Owner. `name`, `city`, auto-generated `join_code` (unused by
   this flow, but required/unique on the model).
3. **Batches** (2–3) — e.g. "Class 10 Maths" (Mon/Wed/Fri) and "Class 12 Physics" (Tue/Thu/Sat),
   each with a `FeeStructure` (`monthly_amount`).
4. **ClassSessions** — a handful of past sessions per batch (last 3–4 weeks), matching each
   batch's schedule.
5. **Parent** — `phone_number = "9999999998"`, `institute_id` set, `user_id = NULL` (the invite
   stub shape from §3). Create if absent; if a row exists from a prior real Test-OTP login
   (`user_id` already set), leave `user_id` alone and only fill in missing fields.
6. **Student** — `parent_id` + `institute_id` set.
7. **Enrollment(s)** — student enrolled in 1–2 of the seeded batches.
8. **Attendance** — one row per `(enrollment, session)` for sessions on/after enrollment,
   mostly `PRESENT` with a couple `ABSENT` for realism.
9. **FeeRecord**s — 2–3 months per enrollment, mix of `FULLY_PAID` and `NOT_PAID`.

Response: summary of what was created vs. already-existing (counts per entity), so re-running it
is informative rather than silent.

### 4.2 No changes to auth code

`auth_service.py`, `owner_service.py`, `parent_service.py` OTP/JWT logic is untouched. The seed
endpoint only writes rows through the normal repository layer — the exact same tables and
constraints real signups use.

---

## 5. Mobile changes (`BATCHBOOK_APP`)

### 5.1 New screens — student OTP login

Two new files under `src/app/(auth)/`, mirroring the existing owner flow
(`phone-login.tsx` / `otp-verification.tsx`) as separate screens (not a shared `role`-parameterized
screen — the post-verify branching genuinely diverges: owner does an institute-exists check with
two possible redirects, student just writes three `AsyncStorage` keys and redirects once):

- **`student-phone-login.tsx`** — same 10-digit validation as `phone-login.tsx`;
  `POST /parent/generate_otp`; navigates to `student-otp-verification` with `phone` param.
- **`student-otp-verification.tsx`** — same OTP-entry/auto-verify UX as `otp-verification.tsx`;
  `POST /parent/verify_otp`; on success:
  1. `supabase.auth.setSession({ access_token, refresh_token })` from the response.
  2. `AsyncStorage.setItem('bb_role', 'student')`.
  3. `AsyncStorage.setItem('bb_student_id', String(children[0].id))` and
     `AsyncStorage.setItem('bb_student_name', children[0].name ?? '')` from the response's
     `children` array — mirrors exactly what `batchbookui`'s `PhoneOtpStep.jsx` already does for
     web.
  4. `router.replace('/(student)/home')`.
  - Resend logic identical to the owner screen (60s countdown, re-POST generate_otp).

### 5.2 Wire the dead end

`src/app/(auth)/onboarding.tsx` — for `profile.role === 'student'`, `handleContinue` currently
falls through with no navigation (step 3 just shows a static "ask your tutor" card). Change it to
route to `/(auth)/student-phone-login` the same way the owner branch already routes to
`/(auth)/phone-login`.

### 5.3 No changes needed elsewhere

`(student)/_layout.tsx`'s route guard (redirect to landing if no session, redirect to onboarding
if role mismatch) and `StudentDataContext`'s use of `AsyncStorage`'s `bb_student_id`/
`bb_student_name` already work correctly once the two keys above are set — this was confirmed by
reading both files; no gaps found downstream of login.

---

## 6. Web (`batchbookui`)

No changes. `PhoneLogin.jsx`/`OtpVerification.jsx` (owner) and `PhoneOtpStep.jsx` (student/parent)
already work for any phone number, including the two test numbers, once Supabase Test OTP is
configured correctly (confirmed working as of 2026-07-10).

---

## 7. Testing

### Backend (pytest)
- `POST /admin/seed-demo-accounts` without `X-Admin-Secret` → 401; with wrong secret → 401.
- First call creates all rows (Owner, Institute, 2+ Batches, Parent stub with `user_id IS NULL`,
  Student, Enrollments, Attendance, FeeRecords) with correct linkage — no orphan rows.
- Second call is a no-op on already-correct rows (idempotency) — assert no duplicate
  Owner/Institute/Parent/Student rows by phone/name.
- Running it after a real Test-OTP login has already attached `Parent.user_id` does not clobber
  that `user_id`.

### Manual verification (both required before considering this done)
- Web: log in as `9999999999` and `9999999998` against a seeded environment; confirm batches,
  attendance, and fee screens render populated data for both roles.
- Mobile (`BATCHBOOK_APP`): same two logins, on-device or simulator — confirm the new student
  screens navigate correctly and `(student)/home` renders seeded data; confirm owner flow still
  works unchanged.

---

## 8. Delivery

- **Backend:** branch off `master` in `BatchBook`, PR. No Alembic migration needed — no schema
  changes, only a new route + data-seeding service logic.
- **Mobile:** committed in the `BATCHBOOK_APP` repo (separate repo, not a submodule of
  `BatchBook`) on its own branch + PR.
- **Pre-submission checklist:**
  1. Confirm Supabase Test OTP numbers/format still correct (`919999999999` / `919999999998`,
     valid through 2026-08-31 — renew before then if review is still pending).
  2. Call `POST /admin/seed-demo-accounts` against the **production** `DATABASE_URL`.
  3. Manually walk both logins on the actual Play Store build before submitting.
  4. In the Play Store listing's "App access" section, supply `9999999999` / OTP `110304` as
     the reviewer credentials for the owner role, and `9999999998` / OTP `110304` for the
     student role, with a note that login is phone+OTP (no password).

---

## 9. Out of scope

- Teacher role — not built yet in `BATCHBOOK_APP` or seeded here; the project owner confirmed
  this is a not-yet-developed feature and reviewers don't need it.
- Any change to real-user OTP/JWT flow, Supabase auth configuration, or rate limiting
  (5/min generate, 10/min verify already applies equally to the test numbers — not adjusted).
- A generic/reusable "seed any demo institute" tool — this endpoint is specifically shaped for
  the two fixed reviewer phone numbers, not a general fixture generator.
- Renewing the Test OTP expiry date automatically — that's a manual Supabase dashboard action
  outside this repo's code, called out as a checklist item in §8 instead.
