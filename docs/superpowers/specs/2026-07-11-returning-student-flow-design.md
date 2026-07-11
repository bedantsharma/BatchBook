# Returning-Student Login & Profile-Completion Flow — Design

**Date:** 2026-07-11
**Trigger:** Neither the website nor the Expo app has a real "returning student" path — every launch
forces a student/parent back through full name/parent-name/parent-phone collection before they can
even reach phone verification, even if they already have a complete account.
**Repos affected:** `BatchBook` (backend + `batchbookui` submodule, this doc). `BATCHBOOK_APP`
(React Native, sibling repo) has its own companion doc:
`BATCHBOOK_APP/docs/superpowers/specs/2026-07-11-returning-student-flow-design.md`. Read both —
they share one backend contract (defined here) and diverge only in per-platform UI wiring.

---

## 1. Problem

Students don't self-register — a tutor invites them (`POST /enrollment/invite`), which creates
`Parent` + `Student` + `Enrollment` rows up front. A parent then "claims" that account via phone
OTP (`POST /parent/verify_otp`), which already **upserts** by phone/Supabase-user-id
(`ParentService.get_or_create_after_otp`, `services/parent_service.py:16-40`). So the backend is
already returning-user-safe at the auth layer — the problem is entirely UX:

- The website's `OnboardingWizard` hard-requires parent name + parent phone (`ParentDetailsStep`)
  before it will even send an OTP, for every visit, every time — even for a parent who already has
  a fully-filled-in profile.
- The Expo app collects student name / parent name / parent phone in `onboarding.tsx` before
  routing to OTP, but never actually sends that data to the backend — it's pure UI theater.
- Neither app distinguishes "I already told you everything" from "you're missing details" — it's
  all-or-nothing, every time.
- Neither app's launch-time session gate falls back gracefully when a valid Supabase session
  exists but the locally-cached role is gone (cleared storage, new device) — it just re-runs the
  whole flow instead of asking the backend who this session belongs to.

## 2. Core model

There is no real "new vs. returning" fork after OTP verification. A parent either:
- has **zero** linked children → no tutor has invited this number yet → blocked
  ("ask your tutor to add you first"), **unchanged behavior**.
- has **≥1** linked children → whether this is their very first login after an invite, or their
  hundredth, the only thing that matters is: **is any profile field still null?**

So one unified check, run immediately after a successful OTP verify, replaces both the old
pre-OTP form and the "first login after invite" special case. A parent who taps the WhatsApp
`enrollment_invite` link and verifies for the first time lands on the exact same phone → OTP →
missing-field-check path as a long-time returning parent — the missing-field step is just more
likely to have something to show them.

**Fields considered "missing"** (any `null`/empty counts):
- `Parent.name`
- `Student.name` (per child) — required at invite time, so rarely actually null, but checked
  defensively
- `Student.email` (per child) — never collected anywhere today, commonly null

No new `Parent.email` column — deliberately out of scope. Only the student's existing (already
nullable) `email` column is used.

## 3. Backend changes

No DB migration needed — every field involved already exists (`Parent.name`, `Student.name`,
`Student.email`).

### 3.1 New endpoints

**`PATCH /parent/update`** (auth required) — mirrors `PATCH /owner/update` exactly.
```
Request:  { "name": "string | null" }
Response: ParentProfileResponse (existing shape: id, name, phone_number, created_at, children[])
```

**`PATCH /parent/children/{student_id}`** (auth required) — update one linked child's name/email.
Ownership-scoped: 403 if `Student.parent_id != current_parent.id`.
```
Request:  { "name": "string | null", "email": "string | null" }   (both optional, patch semantics)
Response: StudentSummary (existing shape: id, name, email, fees_status, institute_id)
```

Route home: `routes/parent_route.py`, service method on `ParentService` (new `update_parent`,
`update_child`), repository methods on `ParentRepository`/`StudentRepository` for the scoped
lookup + update.

### 3.2 Response shape extensions (avoid a second round-trip after OTP verify)

`VerifyParentResponse` (`POST /parent/verify_otp`, `POST /student/verify_otp`) currently has no
parent-level `name` and no `email` per child. Add both so the client can compute "what's missing"
directly from the verify response, without an extra `GET /parent/me` call:

```
VerifyParentResponse {
  auth_token, refresh_token, aud, user_id,
  parent_name: string | null,          # NEW
  children: [
    { id, name, email: string | null,  # email is NEW
      fees_status }
  ]
}
```

`ParentProfileResponse` (`GET /parent/me`) already has `parent.name` and `child.email` — no
change needed there; it's used as the fallback for the session-restore case (§5).

### 3.3 Tests

- `PATCH /parent/update`: happy path, auth-required 401, partial-field patch semantics.
- `PATCH /parent/children/{id}`: happy path, ownership 403 (child belongs to a different parent),
  404 for non-existent child.
- `POST /parent/verify_otp`: response now includes `parent_name` and `children[].email`.

## 4. Website (`batchbookui`) changes

- `OnboardingWizard.jsx` — student step list changes from
  `['role', 'profile', 'parentDetails', 'parentOtp']` to `['role', 'phone', 'otp']`. Drop
  `ParentDetailsStep`'s hard-required parent name + phone gate entirely; `ProfileStep`
  (student name/email, already optional) is also dropped from the pre-OTP path since it's never
  sent to the backend anyway.
- Phone-entry step (new, replacing `ParentDetailsStep`'s phone field) keeps the existing hint
  copy ("Parent's mobile number") but the field is a plain 10-digit input — no name field, no
  hard gate beyond phone-format validation.
- `PhoneOtpStep.jsx` — after a successful verify: zero children → unchanged blocker copy. Else,
  compute missing fields from the (now-extended) verify response. If anything is missing, render
  a new `CompleteProfileStep` (only the missing fields — parent name and/or child name/email),
  submit via `PATCH /parent/update` / `PATCH /parent/children/{id}`, then redirect to
  `/dashboard/student`. If nothing is missing, redirect immediately.
- This is also the path a parent lands on from the WhatsApp `enrollment_invite` link — no special
  casing needed, confirm during implementation that the link doesn't deep-link anywhere unusual.

## 5. Session-restore fallback (both website and mobile)

Today, `StudentRoute.jsx` requires `localStorage.bb_role === 'student'` *in addition to* a live
Supabase session — if `bb_role` is missing (cleared storage, different browser/device with a
still-valid Supabase session), it redirects straight to `/onboarding`, forcing the whole flow
again for someone who's already authenticated.

**Fix:** if a valid Supabase session exists but `bb_role` is missing, call `GET /parent/me`
before giving up:
- 200 → this is a student session; stamp `bb_role`/`bb_student_id`/`bb_student_name` from the
  response, run the same missing-field check as §2, then proceed to `/dashboard/student` (with
  `CompleteProfileStep` first if needed).
- 401/expired → fall back to `/onboarding` as today.

(Mobile-side equivalent is specified in the `BATCHBOOK_APP` companion doc — same backend contract,
`src/app/index.tsx` instead of `StudentRoute.jsx`.)

## 6. Error handling

- Zero-children blocker: unchanged.
- Missing-field `PATCH` failures: inline retry — the auth token is already issued, so a failed
  save is just a retry, never a re-auth.
- Ownership check on `PATCH /parent/children/{id}` prevents a parent editing a child that isn't
  theirs (403, not a 500 or silent no-op).

## 7. Testing

- Backend: unit tests per §3.3.
- Website: manual QA of both paths — (a) fully-complete returning parent: phone → OTP → straight
  to dashboard, no extra screen; (b) incomplete profile (freshly invited or historically
  incomplete): phone → OTP → `CompleteProfileStep` → dashboard. Also verify the session-restore
  fallback (§5) with `bb_role` manually cleared from `localStorage` while a session cookie/token
  is still valid.
