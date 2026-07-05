### PHASE A — Fix Ship-Blockers 🟡 PARTIAL (A.3 pending manual test)

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

### ✅ All 3 bugs fixed (confirmed in code 2026-07-03)

- **Owner path on `/onboarding`:** `RoleStep.jsx` now has a third card — `Owner / Institute` (`id: 'owner'`), not disabled. Selecting it and continuing routes to `/phone-login` via `OnboardingWizard.jsx`'s `next()` check (`if (data.role === 'owner') navigate('/phone-login')`).
- **OTP resend bug:** `OtpVerification.jsx`'s `handleResendOtp()` calls `setOtp('')` and `setIsResending(false)` after a successful resend, clearing the stale digits and re-enabling the (previously `disabled={isLoading || isResending}`) digit inputs so the new code can be typed and verified.
- **Parent/student sign-out:** Sign-out is now centralized in `AuthContext.jsx`'s `signOut()`, which clears all 4 keys (`bb_role`, `bb_student_id`, `bb_student_name`, `onboarding_profile`) and calls `supabase.auth.signOut()`. Both `StudentDashboard.jsx` and `OwnerDashboard.jsx` (and the legacy `Dashboard.jsx`) call this same shared function, so parent sign-out matches student sign-out behavior.

Shipped across `fix/a3-bugs` commits in `batchbookui` (8780e39, 3db1f88, c90670b bumps in `BatchBook`). Not yet re-run live end-to-end since the fix — worth a quick manual pass alongside Task C.5, but no longer blocking.

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

**Verified by:** _(verified by bedant)_