# BatchBook UI — Auth Handover

> **For the next Claude Code session.** Read this top-to-bottom before touching any file.

---

## Current Branch

```
feature/owner-dashboard-shell
```

Do **not** switch branches or open a PR until the auth work described below is complete and manually tested end-to-end.

---

## What BatchBook Is (30-second version)

A SaaS product for India's small coaching institutes. Two user types:

| User | Login path | Dashboard |
|------|-----------|-----------|
| **Owner** (teacher/institute owner) | `/phone-login` → OTP → `/owner/dashboard` | Desktop sidebar layout |
| **Student/Parent** | `/onboarding` wizard → OTP step | `/dashboard/student` |

Backend: FastAPI + PostgreSQL (Supabase). Frontend: React 19 + MUI.

---

## The Problem Statement

After merging `master` into `feature/owner-dashboard-shell`, the auth regressed back to Firebase. The frontend now has **two auth systems fighting each other** and neither works correctly:

### Symptom 1 — App.jsx has no `<AuthProvider>`

`AuthContext.jsx` exports `useAuth()` which reads from a React context provided by `<AuthProvider>`. But `App.jsx` never wraps the app in `<AuthProvider>`. Any component calling `useAuth()` (including `ProtectedRoute`) will either get `null` or throw.

### Symptom 2 — Login routes redirect to "/" instead of rendering

In the current `App.jsx`:
```jsx
{/* Legacy redirects */}
<Route path="/phone-login" element={<Navigate to="/" replace />} />
<Route path="/otp-verification" element={<Navigate to="/" replace />} />
```
The owner cannot log in at all — the login page never renders.

### Symptom 3 — Backend tokens never reach Supabase client

`PhoneOtpStep.jsx` (onboarding) and `OtpVerification.jsx` (owner login) both:
1. Call the backend (`/student/verify_otp` or `/owner/verify_otp`)
2. Receive `{ auth_token, refresh_token, user_id }` back
3. **Store tokens only in localStorage** — never call `supabase.auth.setSession()`

`AuthContext.jsx` reads `supabase.auth.getSession()`. Because `setSession()` was never called, the Supabase client has no idea a login happened. `session` stays `null`. Every `<ProtectedRoute>` redirects to `/phone-login` (which itself redirects to `/`). Infinite loop.

### Symptom 4 — `PhoneLogin.jsx` calls the wrong backend endpoint

`PhoneLogin.jsx` is the **owner** login entry point. It currently calls `/student/generate_otp`. It should call `/owner/generate_otp`.

### Symptom 5 — `firebaseconfig.ts` and `firebase` npm package still exist

`firebaseconfig.ts` is a dead file. The `firebase` npm package is still in `package.json` (version `^12.12.0`). Nothing imports `firebaseconfig.ts` anymore, but the dependency is dead weight and causes confusion.

---

## What the Backend Returns (important)

After OTP verification, both `/student/verify_otp` and `/owner/verify_otp` return:

```json
{
  "auth_token": "<Supabase JWT access token>",
  "refresh_token": "<Supabase refresh token>",
  "user_id": "<UUID>"
}
```

`auth_token` **is a real Supabase JWT** — the backend calls Supabase Auth internally and proxies the token back. This means we can call:

```js
await supabase.auth.setSession({
  access_token: auth_token,
  refresh_token: refresh_token,
})
```

...and the Supabase JS client will immediately have a valid session. `AuthContext` will pick it up via `onAuthStateChange`. This is the bridge that makes everything work.

---

## The Target State

After the fix, auth should work as follows:

### Owner Login Flow
```
/ (LandingPage)
  └─ click "Login as Owner" (or navigate directly)
/phone-login  →  PhoneLogin.jsx
  └─ enter 10-digit number
  └─ POST /owner/generate_otp  →  OTP sent to phone
/otp-verification  →  OtpVerification.jsx
  └─ enter 6-digit OTP
  └─ POST /owner/verify_otp  →  { auth_token, refresh_token, user_id }
  └─ supabase.auth.setSession(auth_token, refresh_token)  ← THE KEY CALL
  └─ navigate to /owner/dashboard
/owner/dashboard  →  OwnerDashboard.jsx (protected)
```

### Student/Parent Onboarding Flow
```
/onboarding  →  OnboardingWizard.jsx
  └─ role / profile / parentDetails steps
  └─ PhoneOtpStep.jsx  (parentOtp or teacherOtp step)
     └─ POST /student/generate_otp  →  OTP sent
     └─ POST /student/verify_otp  →  { auth_token, refresh_token, user_id }
     └─ supabase.auth.setSession(auth_token, refresh_token)  ← THE KEY CALL
     └─ onSuccess(phone)  →  navigate to /dashboard/student or /dashboard/teacher
```

### AuthContext (no changes needed — already correct)
```js
supabase.auth.getSession()        // picks up session on page load
supabase.auth.onAuthStateChange() // picks up session after setSession() call
```

---

## Exact Files to Change

### 1. `src/App.jsx` — Three changes

**a) Import and add `<AuthProvider>`:**
```jsx
import { AuthProvider } from './context/AuthContext';
// wrap <Router>...</Router> inside <AuthProvider>
```

**b) Import and add protected routes for all dashboard pages:**
```jsx
import ProtectedRoute from './components/ProtectedRoute';
import PhoneLogin from './components/PhoneLogin';
import OtpVerification from './components/OtpVerification';
import OwnerDashboard from './pages/owner/OwnerDashboard';
import OwnerSetup from './pages/owner/OwnerSetup';
```

**c) Replace the "legacy redirect" routes with real routes:**
```jsx
// REMOVE these:
<Route path="/phone-login" element={<Navigate to="/" replace />} />
<Route path="/otp-verification" element={<Navigate to="/" replace />} />

// ADD these:
<Route path="/phone-login" element={<PhoneLogin />} />
<Route path="/otp-verification" element={<OtpVerification />} />
<Route path="/owner/setup" element={<ProtectedRoute><OwnerSetup /></ProtectedRoute>} />
<Route path="/owner/dashboard" element={<ProtectedRoute><OwnerDashboard /></ProtectedRoute>} />

// Also wrap existing dashboard routes:
<Route path="/dashboard/teacher" element={<ProtectedRoute><TeacherDashboard /></ProtectedRoute>} />
<Route path="/dashboard/student" element={<ProtectedRoute><StudentDashboard /></ProtectedRoute>} />
```

---

### 2. `src/components/PhoneLogin.jsx` — Change one endpoint

Line 40 currently:
```js
const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/student/generate_otp`, {
```
Change to:
```js
const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/owner/generate_otp`, {
```

---

### 3. `src/components/OtpVerification.jsx` — Two changes

**a) Change endpoint (line 76):**
```js
// FROM:
const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/student/verify_otp`, {
// TO:
const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/owner/verify_otp`, {
```

**b) After getting tokens, call `setSession` before navigating (replace lines 87–93):**
```js
const { auth_token, refresh_token, user_id } = await res.json();

// Bridge the backend Supabase JWT into the Supabase JS client
const { error: sessionError } = await supabase.auth.setSession({
  access_token: auth_token,
  refresh_token: refresh_token,
});
if (sessionError) throw sessionError;

// AuthContext will pick up the session via onAuthStateChange
navigate('/owner/dashboard');
```

Import supabase at the top:
```js
import { supabase } from '../lib/supabaseClient';
```

Remove the `localStorage.setItem` calls for `auth_token`, `refresh_token`, `user_id` — the Supabase client manages the session now.

---

### 4. `src/components/onboarding/PhoneOtpStep.jsx` — Add `setSession` call

In the `verifyOtp` function (around line 63), after getting tokens:
```js
const { auth_token, refresh_token, user_id } = await res.json();

// Bridge the backend Supabase JWT into the Supabase JS client
const { error: sessionError } = await supabase.auth.setSession({
  access_token: auth_token,
  refresh_token: refresh_token,
});
if (sessionError) throw sessionError;

onSuccess(phone);
```

Import supabase at the top:
```js
import { supabase } from '../../lib/supabaseClient';
```

Remove the `localStorage.setItem` calls — no longer needed.

---

### 5. Delete `src/firebaseconfig.ts`

```bash
rm src/firebaseconfig.ts
```

---

### 6. Uninstall Firebase npm package

```bash
npm uninstall firebase
```

---

## Files That Are Already Correct — Do NOT Change

| File | Why it's fine |
|------|--------------|
| `src/context/AuthContext.jsx` | Already uses `supabase.auth.getSession()` + `onAuthStateChange` |
| `src/lib/supabaseClient.js` | Already configured with env vars |
| `src/services/api.js` | Already attaches Supabase JWT to every axios request |
| `src/components/ProtectedRoute.jsx` | Already reads `session` from `useAuth()` correctly |

---

## End-to-End Test Checklist

After making all changes, verify each step manually:

- [ ] `npm run dev` starts without Firebase import errors
- [ ] Navigate to `http://localhost:5173/phone-login` — PhoneLogin page renders (not redirected)
- [ ] Enter your phone number → OTP received on phone (backend must be running: `uvicorn app:app --reload --port 8000`)
- [ ] Enter OTP → verify → no errors → redirected to `/owner/dashboard`
- [ ] Refresh `/owner/dashboard` — stays on dashboard (session persists via Supabase)
- [ ] Open DevTools → Application → Local Storage — no raw `auth_token` keys (session is in Supabase's own storage)
- [ ] Navigate to `http://localhost:5173/phone-login` while logged in → should redirect to dashboard (already authenticated)
- [ ] Sign out → redirected to `/phone-login`
- [ ] Navigate to `http://localhost:5173/onboarding` → complete wizard → PhoneOtpStep → OTP → verify → lands on student/teacher dashboard

---

## Environment Variables Required

Make sure `.env` in the project root has:
```
VITE_SUPABASE_URL=https://wtckiivxgouyqweeieuc.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key from backend .env or Supabase dashboard>
VITE_API_BASE_URL=http://localhost:8000
```

The `.env` file exists already — verify the values are filled in (not placeholders).

---

## Context on the Broader Roadmap

This fix completes **Task 1.5** from the project roadmap (`docs/` folder has the full spec). The next task after this fix is **Task 1.6** — wiring up the Owner dashboard pages (Batches, Students, Fees, Attendance sidebars). That work is already scaffolded in `src/pages/owner/OwnerDashboard.jsx` and `src/pages/owner/OwnerSetup.jsx`.

Do not start Task 1.6 until the end-to-end test checklist above passes completely.

---

## Backend Must Be Running

The frontend auth calls the backend. Before testing, start it:

```bash
cd ~/PycharmProjects/BatchBook
source .venv/bin/activate
uvicorn app:app --reload --port 8000
```

The owner endpoints (`/owner/generate_otp`, `/owner/verify_otp`) were completed in Task 1.1 and are already working. Confirm at `http://localhost:8000/docs`.
