# BatchBook — Stabilization & Agent Guardrails Design

**Date:** 2026-06-03  
**Status:** Approved by owner  
**Scope:** Three-task stabilization sprint (Phase 0) + roadmap status corrections + nightly agent prompt guardrails

---

## Problem Statement

The nightly agent has been building features in isolation and marking tasks "done" the moment a draft PR is created. The result is a codebase where:

- The backend has 221 passing tests and all endpoints implemented
- The owner dashboard frontend is connected to real APIs
- But the student dashboard is 100% mock data (PR #22 was a draft, never merged)
- `ProtectedRoute` has zero role enforcement — any logged-in user can reach any dashboard
- The owner has no setup gate — skips institute creation entirely if they navigate directly
- The teacher login calls `/student/verify_otp` — wrong endpoint
- The nightly agent has no pre-flight check, so it builds new features on top of this broken foundation

**The fix:** Add Phase 0 (three integration tasks that must complete before new feature work resumes) + update the roadmap to reflect honest status + add pre-flight protocol to the agent.

---

## MVP Scope Decision

**Primary user (MVP):** Solo tutor who is simultaneously the owner AND the teacher. They manage their own batches, mark their own attendance, collect their own fees — all from the Owner Dashboard.

**Hired teachers:** Important long-term feature. Leave connection space (Teacher model + routes already exist in backend). Do not invest in the Teacher Dashboard UI until teacher MVP is formally scoped.

**Implication:** The Teacher Dashboard at `/dashboard/teacher` (currently 100% mock data) is a placeholder stub. Disable the teacher option in the OnboardingWizard for now rather than routing to a non-functional dashboard.

---

## Section 1 — Status Taxonomy

All roadmap task status labels are replaced with these five:

| Symbol | Label | Meaning |
|--------|-------|---------|
| ✅ | `INTEGRATED` | PR merged to master, feature manually verified working in browser or via curl |
| 🟡 | `PR-OPEN` | Code written, PR exists, **not yet merged** to master |
| 🔧 | `PARTIAL` | Some sub-tasks merged and working, others missing |
| ⬜ | `NOT-STARTED` | Not touched |
| 🚫 | `BLOCKED` | Waiting on external credential, API access, or template approval |

Every task heading in the roadmap gets exactly one of these labels. No more unmarked tasks.

---

## Section 2 — Phase 0: Integration Stabilization

**Rule:** The nightly agent must complete ALL Phase 0 tasks (reach `INTEGRATED` status) before picking any Phase 1–6 task. Phase 0 tasks are ordered — complete them in sequence.

---

### Task 0.1 — Role-aware routing ⬜ NOT-STARTED

**Why:** Any logged-in user can currently reach any dashboard by typing its URL. An owner who types `/dashboard/student` sees the student dashboard. A parent who types `/owner/dashboard` sees the owner dashboard. This makes the product fundamentally broken for multi-user use.

**Exact changes:**

| File | Change |
|------|--------|
| `batchbookui/src/components/OtpVerification.jsx` | After `supabase.auth.setSession()` succeeds, call `localStorage.setItem('bb_role', 'owner')` before navigating |
| `batchbookui/src/components/onboarding/PhoneOtpStep.jsx` | After `supabase.auth.setSession()` succeeds, call `localStorage.setItem('bb_role', 'student')` before calling `onSuccess()` |
| `batchbookui/src/context/AuthContext.jsx` | Expose `role` (read from localStorage on init). Clear it in `signOut()`. |
| New: `batchbookui/src/components/OwnerRoute.jsx` | Replaces `ProtectedRoute` on owner routes. Checks both session AND `role === 'owner'`. No session → `/phone-login`. Session but wrong role → `/phone-login`. Correct role → renders children. |
| New: `batchbookui/src/components/StudentRoute.jsx` | Replaces `ProtectedRoute` on student routes. Checks both session AND `role === 'student'`. No session → `/onboarding`. Session but wrong role → `/onboarding`. Correct role → renders children. |
| `batchbookui/src/App.jsx` | `/owner/setup` and `/owner/dashboard` routes use `<OwnerRoute>`. `/dashboard/student` uses `<StudentRoute>`. `/dashboard/teacher` renders a "Teacher access coming soon" placeholder (not a protected route — no auth needed to see a static message). |
| `batchbookui/src/components/onboarding/OnboardingWizard.jsx` | Teacher role option: show a disabled card with tooltip "Teacher login coming soon — ask your institute owner to invite you." Do not call any OTP endpoint. Do not navigate to `/dashboard/teacher`. |

**Verified by:**
- Owner logs in via `/phone-login` → open new tab → navigate to `/dashboard/student` → lands on `/phone-login` (redirected)
- Student logs in via `/onboarding` → open new tab → navigate to `/owner/dashboard` → lands on `/onboarding` (redirected)
- No session → navigate to `/owner/dashboard` → lands on `/phone-login`

---

### Task 0.2 — Owner setup gate ⬜ NOT-STARTED

**Why:** A new owner who completes OTP verification bypasses institute setup entirely. `OtpVerification.jsx` hardcodes `navigate('/owner/dashboard')`. An owner with no institute will see the dashboard but every API call that requires `institute_id` will fail.

**Exact changes:**

| File | Change |
|------|--------|
| `batchbookui/src/components/OtpVerification.jsx` | After `setSession()` succeeds, call `GET /owner/institute` using the new JWT. On 404 → `navigate('/owner/setup')`. On 200 → `navigate('/owner/dashboard')`. Replace the current hardcoded `navigate('/owner/dashboard')` line. |

No backend changes needed — `GET /owner/institute` already returns 404 for owners with no institute.

**Verified by:**
- Create a fresh Supabase test user (a phone number not in the Owner table). Complete OTP → lands on `/owner/setup`.
- Existing owner with institute → completes OTP → lands on `/owner/dashboard` directly.

---

### Task 0.3 — Student dashboard live data ⬜ NOT-STARTED

**Why:** `dashboardService.js` on master branch is 100% hardcoded mock data with `setTimeout(300ms)` delays. PR #22 was a draft to fix this but was never merged. Every student who logs in sees fake data.

**Step 1 — Evaluate PR #22:**
Read the PR diff. If it has no merge conflicts against current master (i.e. `git merge --no-commit --no-ff` succeeds): merge it, then verify the result. If it has merge conflicts or its approach is outdated: close it and proceed to steps 2 and 3 to redo the work cleanly.

> **Note:** Task 0.3 is the same work as Phase 5 (Tasks 5.1 + 5.2 in the roadmap). Once Task 0.3 is marked INTEGRATED, also mark Phase 5 Tasks 5.1 and 5.2 as ✅ INTEGRATED.

**Step 2 — Backend: student-facing read APIs**

New file: `BatchBook/routes/student_dashboard_route.py`

| Endpoint | Returns |
|----------|---------|
| `GET /student/me/attendance?month=YYYY-MM` | `{present, total, percentage, sessions: [{date, topic, status}]}` |
| `GET /student/me/fee?month=YYYY-MM` | `{status, amount_due, amount_paid, due_day, payment_link?}` |
| `GET /student/me/schedule?date=YYYY-MM-DD` | `[{batch_name, subject, start_time, end_time}]` for that date |
| `GET /student/me/upcoming-events?limit=10` | Next N sessions across all the student's enrollments |

Auth: uses `get_current_user_id` from `auth_service.py` (same pattern as existing routes). The `user_id` maps to a `Parent` record, which has `Student` children, which have `Enrollment` records.

Register router in `app.py`.

**Step 3 — Frontend: replace mock data**

File: `batchbookui/src/services/dashboardService.js`

Replace every `setTimeout(hardcoded, 300)` with real `api.js` calls to the new endpoints. Add proper loading and error states in the components that consume this service.

**Verified by:**
- Enroll a real student (or use an existing one) in a batch with sessions recorded.
- Student logs in → attendance tab shows real session count from DB, not "18/22".
- Fee tab shows the student's actual payment status.

---

## Section 3 — Existing Phase Status Corrections

Update the roadmap overview table and each phase header:

| Phase | Old Status | New Status | Notes |
|-------|-----------|-----------|-------|
| 1 | ✅ Complete | ✅ INTEGRATED (with gaps) | All backend tasks INTEGRATED. Frontend tasks INTEGRATED. Gaps: no role routing, no setup gate — addressed in Phase 0. |
| 2 | ✅ Complete | ✅ INTEGRATED | Batch/enrollment backend + Batches/Students UI pages all wired to real API. |
| 3 | 🟡 Partial | 🟡 PARTIAL | 3.1 ✅ INTEGRATED, 3.2 ✅ INTEGRATED, 3.3 ✅ INTEGRATED, 3.4 🚫 BLOCKED (WATI), 3.5 ✅ INTEGRATED |
| 4 | 🟡 Partial | 🟡 PARTIAL | 4.1 ✅ INTEGRATED, 4.2 🚫 BLOCKED (WATI), 4.3 ✅ INTEGRATED, 4.4 ✅ INTEGRATED |
| 5 | ❌ Not started | ⬜ NOT-STARTED | Draft PR #22 exists but never merged. Handled in Phase 0.3. |
| 6 | 🟡 Partial | 🟡 PARTIAL | 6.1 ✅ INTEGRATED, 6.2 ✅ INTEGRATED, 6.3 🔧 PARTIAL (score entry done; header stats not wired), 6.4 ✅ INTEGRATED |

Add to the "Frontend — What Is Missing" section of the roadmap:

```
### Known Integration Gaps (fixed in Phase 0)
- **ProtectedRoute has no role enforcement**: any logged-in user can reach any dashboard via URL.
  Fix: Task 0.1 adds OwnerRoute + StudentRoute with role checks.
- **Owner has no setup gate**: new owner bypasses institute creation, causing silent API failures.
  Fix: Task 0.2 adds a post-login institute check in OtpVerification.jsx.
- **Teacher option in OnboardingWizard calls wrong endpoint**: uses /student/verify_otp for teachers.
  Fix: Task 0.1 disables the teacher option entirely (teacher login is out of MVP scope).
- **Student dashboard is mock data on master**: PR #22 was a draft, never merged.
  Fix: Task 0.3 wires dashboardService.js to real backend.
```

---

## Section 4 — Nightly Agent Prompt Changes

### 4a — Pre-flight Checklist

Add this block at the **top** of the agent prompt, before any task-picking logic:

```
## PRE-FLIGHT — Run every session before picking any task

Step 1: Start from clean master
  git checkout master && git pull origin master
  → Must be on clean master with no uncommitted changes.

Step 2: Conflict marker scan
  grep -rn "<<<<<<" --include="*.py" --include="*.jsx" --include="*.js" --include="*.ts" .
  → If ANY conflict markers found:
    Fix the conflicts, open a PR titled "fix: resolve conflict markers in <file>", end session.
    Do NOT start a new feature task.

Step 3: Test suite
  cd ~/PycharmProjects/BatchBook && uv run pytest -q
  → If tests fail:
    Fix the failures (do not skip or mark xfail without a comment explaining why).
    Open a PR with the fix, end session.
    Do NOT start a new feature task.

Step 4: Last task status check
  Read BATCHBOOK_ROADMAP.md. Find the most recently modified task.
  → If it is marked PR-OPEN: do not start a new task.
    Write in your session summary: "PR [#N] from last session needs review and merge before next task."
    End session.
  → If it is marked INTEGRATED: proceed to Step 5.
  → If it is marked PARTIAL and you can complete it cheaply (< 30 min): complete it before starting anything new.

Step 5: Pick the first NOT-STARTED task
  Scan phases top-to-bottom. Pick the first ⬜ NOT-STARTED task.
  Skip 🚫 BLOCKED tasks.
  Phase 0 tasks have priority over all other phases — complete them in order (0.1, then 0.2, then 0.3).
```

### 4b — Definition of INTEGRATED

Add this block to the roadmap (visible to the agent) and reference it in the agent prompt:

```
## Definition of INTEGRATED

A task earns ✅ INTEGRATED only when ALL four conditions are true:

1. The PR is merged to master — not open, not draft, not "ready for review". Merged.
2. uv run pytest -v passes with zero failures after the merge.
3. The feature was manually verified:
   - Backend task: at least one real curl/httpie call hit the endpoint and returned expected data
     (include the command and output in the PR description or a comment)
   - Frontend task: describe exactly what a user sees when the feature works correctly
     (e.g. "Owner with no institute → /owner/setup page appears after OTP. Existing owner → dashboard.")
4. This roadmap task has a "Verified by:" line written in the checklist.

Marking a task INTEGRATED when its PR is open or draft is a roadmap bug.
The agent must not do this.
```

---

## What Comes After Phase 0

Once all three Phase 0 tasks are INTEGRATED, the product has a working end-to-end loop for two user types:

- Owner: logs in → (setup if new) → dashboard → creates batch → adds student → marks attendance → tracks fees
- Student/Parent: logs in → sees real attendance, fee status, schedule

**Phases already covered by Phase 0:**
- Phase 5 (Tasks 5.1 + 5.2) is completed by Task 0.3. Mark both as INTEGRATED after Task 0.3.

**After Phase 0, resume in this order:**
1. Phase 6.3 — wire up Owner Dashboard header stats ("X students | ₹Y | Z% attendance")
2. Phase 3.4 + 4.2 — WATI WhatsApp integration (when credentials arrive)
3. Any remaining PARTIAL tasks

The Teacher Dashboard remains a stub until hired-teacher MVP is formally designed. Do not invest in it before then.

The Teacher Dashboard remains a stub until hired-teacher MVP is formally designed. Do not invest in it before then.
