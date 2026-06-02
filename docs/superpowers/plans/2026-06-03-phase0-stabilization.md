# Phase 0 — Stabilization Sprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the three integration gaps (role-based routing, owner setup gate, student dashboard live data) and correct the roadmap to reflect honest status, so the nightly agent builds on a solid foundation.

**Architecture:** Two new route guard components — OwnerRoute and StudentRoute — replace the roleless ProtectedRoute on protected paths. They read `bb_role` directly from `localStorage` (not from React state) to avoid the timing issue where state is initialized before the role is stamped post-login. AuthContext is updated to clean localStorage on signOut and on session expiry. The parent login flow is corrected to call `/parent/verify_otp` (not `/student/verify_otp`), which returns the student ID stored in `bb_student_id`. The student dashboard backend is already fully implemented; Task 3 only fixes the frontend.

**Tech Stack:** React 19, React Router DOM 7, MUI 9, FastAPI backend (Python), axios (`api.js`), Supabase JS client, localStorage for role persistence.

**Pre-flight before starting any task:**
```bash
cd ~/PycharmProjects/BatchBook
git checkout master && git pull origin master
grep -rn "<<<<<<" --include="*.py" --include="*.jsx" --include="*.js" .   # must return nothing
uv run pytest -q   # must show all passing
```

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `batchbookui/src/context/AuthContext.jsx` | Clear `bb_role` + `bb_student_id` from localStorage on signOut and session expiry |
| Create | `batchbookui/src/components/OwnerRoute.jsx` | Guard: session + role=owner required |
| Create | `batchbookui/src/components/StudentRoute.jsx` | Guard: session + role=student required |
| Modify | `batchbookui/src/components/OtpVerification.jsx` | Stamp `bb_role=owner`; check institute before navigating |
| Modify | `batchbookui/src/components/onboarding/PhoneOtpStep.jsx` | Call `/parent/verify_otp`; stamp `bb_role=student` + `bb_student_id` |
| Modify | `batchbookui/src/components/onboarding/RoleStep.jsx` | Disable teacher option visually |
| Modify | `batchbookui/src/components/onboarding/OnboardingWizard.jsx` | Block teacher path in wizard logic |
| Modify | `batchbookui/src/App.jsx` | Swap ProtectedRoute for OwnerRoute/StudentRoute; teacher route → static page |
| Modify | `batchbookui/src/services/dashboardService.js` | Replace all mocks with real `api.js` calls |
| Modify | `batchbookui/src/components/student/StudentDashboard.jsx` | Replace PlaceholderContent with real data |
| Modify | `BatchBook/BATCHBOOK_ROADMAP.md` | Add Phase 0, status taxonomy, status corrections |

---

## Task 1: AuthContext — clean localStorage on logout and session expiry

**Files:**
- Modify: `batchbookui/src/context/AuthContext.jsx`

**Why this matters:** OwnerRoute and StudentRoute read role directly from localStorage. If a session expires or the user signs out, localStorage must be cleaned up, or a logged-out user could still pass the role check on the next visit (until they hard-refresh). AuthContext is the right place to own this cleanup.

- [ ] **Step 1.1: Replace the file with the updated version**

```jsx
import { createContext, useContext, useEffect, useState } from 'react';
import { supabase } from '../lib/supabaseClient';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (!session) {
        // Session expired or revoked — clear role and student ID
        localStorage.removeItem('bb_role');
        localStorage.removeItem('bb_student_id');
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = async () => {
    localStorage.removeItem('bb_role');
    localStorage.removeItem('bb_student_id');
    await supabase.auth.signOut();
  };

  const value = {
    session,
    user: session?.user ?? null,
    loading,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
```

- [ ] **Step 1.2: Verify no import errors in dev server**

```bash
cd ~/PycharmProjects/BatchBook
make dev-d
make logs-f
# Expected: no errors mentioning AuthContext or role
```

- [ ] **Step 1.3: Commit**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git add src/context/AuthContext.jsx
git commit -m "feat: add role state to AuthContext (reads bb_role from localStorage)"
```

---

## Task 2: OwnerRoute and StudentRoute components

**Files:**
- Create: `batchbookui/src/components/OwnerRoute.jsx`
- Create: `batchbookui/src/components/StudentRoute.jsx`

**Why role is read from localStorage directly (not from AuthContext state):** After OTP verify, the code does `localStorage.setItem('bb_role', 'owner')` then `navigate('/owner/dashboard')`. If OwnerRoute read `role` from React state, it would see the stale initial value (`null`) because the AuthContext state hasn't been updated — causing an immediate redirect back to login. Reading from `localStorage` directly is always synchronous and current.

- [ ] **Step 2.1: Create OwnerRoute.jsx**

```jsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Box, CircularProgress } from '@mui/material';

/**
 * OwnerRoute — guards any route that requires an authenticated owner.
 *
 * Reads role from localStorage directly (not React state) so the check
 * is always current after login stamps bb_role before navigating.
 */
export default function OwnerRoute({ children }) {
  const { session, loading } = useAuth();
  const role = localStorage.getItem('bb_role');

  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          bgcolor: 'background.default',
        }}
      >
        <CircularProgress color="primary" />
      </Box>
    );
  }

  if (!session || role !== 'owner') {
    return <Navigate to="/phone-login" replace />;
  }

  return children;
}
```

- [ ] **Step 2.2: Create StudentRoute.jsx**

```jsx
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Box, CircularProgress } from '@mui/material';

/**
 * StudentRoute — guards any route that requires an authenticated student/parent.
 *
 * Reads role from localStorage directly (not React state) so the check
 * is always current after login stamps bb_role before navigating.
 */
export default function StudentRoute({ children }) {
  const { session, loading } = useAuth();
  const role = localStorage.getItem('bb_role');

  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '100vh',
          bgcolor: 'background.default',
        }}
      >
        <CircularProgress color="primary" />
      </Box>
    );
  }

  if (!session || role !== 'student') {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
}
```

- [ ] **Step 2.3: Commit**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git add src/components/OwnerRoute.jsx src/components/StudentRoute.jsx
git commit -m "feat: add OwnerRoute and StudentRoute role-aware guards"
```

---

## Task 3: OtpVerification.jsx — stamp owner role + institute gate

**Files:**
- Modify: `batchbookui/src/components/OtpVerification.jsx`

The current `handleVerifyOtp` function calls `setSession` and then does `navigate('/owner/dashboard')` unconditionally. Replace the navigate call with:
1. Stamp `bb_role = 'owner'` in localStorage
2. Call `GET /owner/institute` with the new JWT
3. Navigate to `/owner/setup` on 404, `/owner/dashboard` on 200

- [ ] **Step 3.1: Replace the `handleVerifyOtp` function body**

Find the block starting at `const { auth_token, refresh_token } = await res.json();` and replace everything from there to the end of the try block:

```javascript
      const { auth_token, refresh_token } = await res.json();

      // Bridge backend JWT into the Supabase JS client
      const { error: sessionError } = await supabase.auth.setSession({
        access_token: auth_token,
        refresh_token: refresh_token,
      });
      if (sessionError) throw sessionError;

      // Stamp owner role for OwnerRoute guard
      localStorage.setItem('bb_role', 'owner');

      // Check if owner has an institute — new owners must set one up first
      const instRes = await fetch(`${import.meta.env.VITE_API_BASE_URL}/owner/institute`, {
        headers: { Authorization: `Bearer ${auth_token}` },
      });
      navigate(instRes.ok ? '/owner/dashboard' : '/owner/setup');
```

The old line `navigate('/owner/dashboard');` is removed.

- [ ] **Step 3.2: Manual verification**

1. Create a fresh Supabase test account (use a phone number not yet in the Owner table — easiest: use a different number, or delete the owner record from Supabase dashboard).
2. Go to `http://localhost:5173/phone-login`, enter the phone, verify OTP.
3. Expected: lands on `/owner/setup` (because no institute exists for a new owner).
4. Now use an existing owner account (one that already has an institute).
5. Expected: lands on `/owner/dashboard` directly.
6. Navigate to `http://localhost:5173/dashboard/student` while still logged in as owner.
7. Expected: redirected to `/phone-login` (OwnerRoute in effect after next task).

- [ ] **Step 3.3: Commit**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git add src/components/OtpVerification.jsx
git commit -m "feat: stamp owner role and add institute-existence gate on OTP verify"
```

---

## Task 4: PhoneOtpStep.jsx — fix parent endpoint + stamp student role + student ID

**Files:**
- Modify: `batchbookui/src/components/onboarding/PhoneOtpStep.jsx`

The `verifyOtp` function calls `/student/verify_otp`. The correct endpoint for parent/student login is `/parent/verify_otp`, which returns `{ auth_token, refresh_token, aud, user_id, children: [{ id, name, fees_status }] }`.

- [ ] **Step 4.1: Replace the `verifyOtp` async function**

```javascript
  const verifyOtp = async () => {
    if (otp.length !== 6) { setError('Enter the 6-digit OTP.'); return; }
    setLoading(true); setError('');
    try {
      const res = await fetch(`${API}/parent/verify_otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, token: otp }),
      });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Error ${res.status}`); }
      const { auth_token, refresh_token, children = [] } = await res.json();

      const { error: sessionError } = await supabase.auth.setSession({
        access_token: auth_token,
        refresh_token: refresh_token,
      });
      if (sessionError) throw sessionError;

      // Stamp student role for StudentRoute guard
      localStorage.setItem('bb_role', 'student');
      // Store first child's ID for dashboard API calls
      if (children.length > 0) {
        localStorage.setItem('bb_student_id', String(children[0].id));
      }

      onSuccess(phone);
    } catch (err) {
      setError('OTP verification failed: ' + err.message);
    } finally {
      setLoading(false);
    }
  };
```

- [ ] **Step 4.2: Backend smoke test**

```bash
# Verify /parent/verify_otp exists and accepts the right shape
curl -s http://localhost:8000/docs | grep -A2 "parent/verify_otp"
# Expected: the endpoint appears in the API docs
```

- [ ] **Step 4.3: Manual verification**

1. Go to `http://localhost:5173/onboarding`, select Student, fill in parent details, complete OTP.
2. Open browser DevTools → Application → Local Storage → `http://localhost:5173`.
3. Expected: `bb_role = 'student'` and `bb_student_id = <a number>` are both present.
4. After login, navigate to `http://localhost:5173/owner/dashboard`.
5. Expected: redirected to `/onboarding` (StudentRoute blocks owner access).

- [ ] **Step 4.4: Commit**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git add src/components/onboarding/PhoneOtpStep.jsx
git commit -m "fix: call /parent/verify_otp (not /student), stamp student role and student_id"
```

---

## Task 5: App.jsx + RoleStep + OnboardingWizard — route guards and teacher disable

**Files:**
- Modify: `batchbookui/src/App.jsx`
- Modify: `batchbookui/src/components/onboarding/RoleStep.jsx`
- Modify: `batchbookui/src/components/onboarding/OnboardingWizard.jsx`

- [ ] **Step 5.1: Update App.jsx imports and routes**

Replace the import section (add OwnerRoute, StudentRoute, Typography, Box from MUI; keep existing imports):

```jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import ErrorBoundary from './components/ErrorBoundary';
import OwnerRoute from './components/OwnerRoute';
import StudentRoute from './components/StudentRoute';

import LandingPage from './components/LandingPage';
import NotFoundPage from './components/NotFoundPage';
import PhoneLogin from './components/PhoneLogin';
import OtpVerification from './components/OtpVerification';
import OnboardingWizard from './components/onboarding/OnboardingWizard';
import TeacherDashboard from './components/teacher/TeacherDashboard';
import StudentDashboard from './components/student/StudentDashboard';
import OwnerDashboard from './pages/owner/OwnerDashboard';
import OwnerSetup from './pages/owner/OwnerSetup';
```

Replace the Routes block inside `App()`:

```jsx
      <Routes>
        {/* ── Public routes ─────────────────────────────────── */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/phone-login" element={<PhoneLogin />} />
        <Route path="/otp-verification" element={<OtpVerification />} />
        <Route path="/onboarding" element={<OnboardingWizard />} />

        {/* ── Owner protected routes ────────────────────────── */}
        <Route
          path="/owner/setup"
          element={<OwnerRoute><OwnerSetup /></OwnerRoute>}
        />
        <Route
          path="/owner/dashboard"
          element={<OwnerRoute><OwnerDashboard /></OwnerRoute>}
        />

        {/* ── Student protected route ───────────────────────── */}
        <Route
          path="/dashboard/student"
          element={<StudentRoute><StudentDashboard /></StudentRoute>}
        />

        {/* ── Teacher — coming soon (no auth required) ─────── */}
        <Route
          path="/dashboard/teacher"
          element={
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', bgcolor: 'background.default' }}>
              <Typography color="text.secondary" sx={{ textAlign: 'center', maxWidth: 400, p: 4 }}>
                Teacher access is coming soon.<br />Ask your institute owner to invite you.
              </Typography>
            </Box>
          }
        />

        {/* ── Legacy redirect ───────────────────────────────── */}
        <Route path="/dashboard" element={<Navigate to="/" replace />} />

        {/* ── Catch-all ─────────────────────────────────────── */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
```

The `ProtectedRoute` import can be removed from `App.jsx` (it's no longer used here). Do not delete the file itself — it may be used elsewhere or can be cleaned up later.

- [ ] **Step 5.2: Disable teacher option in RoleStep.jsx**

Replace the entire file:

```jsx
import React from 'react';
import { Box, Typography, Card, Tooltip } from '@mui/material';
import SchoolIcon from '@mui/icons-material/School';
import PersonIcon from '@mui/icons-material/Person';

export default function RoleStep({ value, onChange }) {
  const options = [
    { id: 'student', label: 'Student', sub: "I'm here to learn", Icon: SchoolIcon, disabled: false },
    { id: 'teacher', label: 'Teacher', sub: 'Coming soon — ask your institute owner', Icon: PersonIcon, disabled: true },
  ];

  return (
    <Box>
      <Typography variant="h6" fontWeight={700} gutterBottom>What's your role?</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        This helps us set up the right experience for you.
      </Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {options.map(({ id, label, sub, Icon, disabled }) => {
          const selected = value === id;
          return (
            <Tooltip
              key={id}
              title={disabled ? 'Teacher login is coming soon. Contact your institute owner.' : ''}
              placement="top"
            >
              <Card
                onClick={() => !disabled && onChange(id)}
                sx={{
                  p: 2.5,
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  borderRadius: 3,
                  border: '2px solid',
                  borderColor: selected ? 'primary.main' : 'rgba(255,255,255,0.10)',
                  bgcolor: selected ? 'rgba(187,134,252,0.08)' : 'background.paper',
                  display: 'flex', alignItems: 'center', gap: 2,
                  transition: 'all 0.15s',
                  opacity: disabled ? 0.45 : 1,
                }}
              >
                <Box sx={{ width: 44, height: 44, borderRadius: 2, bgcolor: selected ? 'primary.main' : 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon sx={{ color: selected ? '#1a1a1a' : 'text.secondary', fontSize: 22 }}/>
                </Box>
                <Box>
                  <Typography fontWeight={700} sx={{ color: selected ? 'primary.main' : disabled ? 'text.disabled' : 'text.primary' }}>{label}</Typography>
                  <Typography variant="caption" color="text.secondary">{sub}</Typography>
                </Box>
              </Card>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 5.3: Guard teacher path in OnboardingWizard.jsx**

In `handleOtpSuccess`, remove the teacher branch (teacher is now disabled in RoleStep so this path is unreachable, but add a safety guard):

```javascript
  const handleOtpSuccess = (phone) => {
    const profile = { ...data };
    localStorage.setItem('onboarding_profile', JSON.stringify(profile));
    // Teacher role is disabled in MVP — always route to student dashboard
    navigate('/dashboard/student');
  };
```

- [ ] **Step 5.4: Manual verification**

1. Go to `http://localhost:5173/onboarding`.
2. On the role selection screen, the Teacher card should appear faded (opacity ~0.45) with cursor `not-allowed`.
3. Click the Teacher card — nothing should happen (role stays unselected).
4. Hover over it — tooltip should read "Teacher login is coming soon. Contact your institute owner."
5. Confirm the Student card still works normally.

- [ ] **Step 5.5: Commit**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git add src/App.jsx src/components/onboarding/RoleStep.jsx src/components/onboarding/OnboardingWizard.jsx
git commit -m "feat: role-based route guards, disable teacher option in onboarding (MVP scope)"
```

---

## Task 6: Student dashboard live data

**Files:**
- Modify: `batchbookui/src/services/dashboardService.js`
- Modify: `batchbookui/src/components/student/StudentDashboard.jsx`

**Context:** The backend endpoints already exist (`/student/me/attendance`, `/student/me/fee`, `/student/me/schedule`, `/student/me/upcoming-events`) and are registered in `app.py`. Tests exist at `tests/test_student_dashboard_routes.py`. The frontend just needs to call them.

All endpoints take `student_id` as a required query param. The student's ID is stored in localStorage as `bb_student_id` (set during Task 4).

- [ ] **Step 6.1: Run existing backend tests to confirm endpoints are healthy**

```bash
cd ~/PycharmProjects/BatchBook
uv run pytest tests/test_student_dashboard_routes.py -v
# Expected: all tests pass
```

- [ ] **Step 6.2: Rewrite dashboardService.js**

```javascript
// batchbookui/src/services/dashboardService.js
import api from './api';

const getStudentId = () => {
  const id = localStorage.getItem('bb_student_id');
  if (!id) throw new Error('No student session. Please log in again.');
  return Number(id);
};

const todayIso = () => new Date().toISOString().split('T')[0];
const currentMonthIso = () => new Date().toISOString().substring(0, 7);

export async function getStudentProfile() {
  const { data } = await api.get('/parent/me');
  const child = data.children?.[0] ?? null;
  return {
    id: child?.id ?? null,
    name: child?.name ?? data.name ?? 'Student',
    initials: ((child?.name ?? data.name) || '?').charAt(0).toUpperCase(),
    phone: data.phone_number,
    feeDue: child?.fees_status === 'NOT_PAID' || child?.fees_status === 'PARTIALLY_PAID',
    avatarUrl: null,
  };
}

export async function getAttendance() {
  const studentId = getStudentId();
  const month = currentMonthIso();
  const { data } = await api.get('/student/me/attendance', {
    params: { student_id: studentId, month },
  });
  const totalPresent = data.reduce((s, b) => s + b.present, 0);
  const totalSessions = data.reduce((s, b) => s + b.total, 0);
  return {
    present: totalPresent,
    total: totalSessions,
    streak: 0,
    month: new Date().toLocaleString('en-IN', { month: 'long', year: 'numeric' }),
    batches: data,
  };
}

export async function getUpcomingEvents() {
  const studentId = getStudentId();
  const { data } = await api.get('/student/me/upcoming-events', {
    params: { student_id: studentId, limit: 10 },
  });
  return data.map(e => ({
    id: e.session_id,
    type: 'class',
    label: e.subject,
    day: new Date(e.date + 'T00:00:00').toLocaleDateString('en-IN', {
      weekday: 'short', day: 'numeric', month: 'short',
    }),
    time: e.start_time.substring(0, 5),
    sub: e.batch_name,
    topic: e.topic ?? '',
  }));
}

export async function getTodaySchedule() {
  const studentId = getStudentId();
  const { data } = await api.get('/student/me/schedule', {
    params: { student_id: studentId, date: todayIso() },
  });
  return data.map(s => ({
    id: s.session_id,
    batchName: s.batch_name,
    subject: s.subject,
    time: `${s.start_time.substring(0, 5)}–${s.end_time.substring(0, 5)}`,
    topic: s.topic ?? '',
    attendanceStatus: s.attendance_status,
  }));
}

export async function getUnreadNotificationCount() {
  return 0;
}
```

- [ ] **Step 6.3: Replace PlaceholderContent in StudentDashboard.jsx with real data**

Replace the entire file:

```jsx
// batchbookui/src/components/student/StudentDashboard.jsx
import React, { useEffect, useState } from 'react';
import { useTheme, useMediaQuery } from '@mui/material';
import C, { fonts } from '../../theme/colors';
import { I } from '../shared/DashboardIcons';
import {
  getStudentProfile,
  getAttendance,
  getTodaySchedule,
  getUpcomingEvents,
} from '../../services/dashboardService';
import { useAuth } from '../../context/AuthContext';
import { useNavigate } from 'react-router-dom';

const NAV_ITEMS = [
  { id: 'home',     label: 'Overview', icon: I.home },
  { id: 'batches',  label: 'Batches',  icon: I.batch },
  { id: 'schedule', label: 'Schedule', icon: I.cal },
  { id: 'fees',     label: 'Fees',     icon: I.rupee },
];

function StudentSidebar({ name, onLogout }) {
  return (
    <div style={{ width: 232, background: C.surface, borderRight: `1px solid ${C.outline}`, padding: '20px 14px', display: 'flex', flexDirection: 'column', gap: 4, flexShrink: 0, minHeight: '100vh' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '4px 8px 22px' }}>
        <div style={{ width: 28, height: 28, borderRadius: 8, background: C.secondary, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 900, color: '#1a1a1a' }}>B</div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em', color: C.text, fontFamily: fonts.sans }}>BatchBook</div>
          <div style={{ fontSize: 10, color: C.text2, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: fonts.sans }}>Student</div>
        </div>
      </div>
      {NAV_ITEMS.map(it => {
        const Ico = it.icon;
        const on = it.id === 'home';
        return (
          <button key={it.id} style={{ background: on ? C.primary15 : 'transparent', border: 'none', borderRadius: 10, cursor: on ? 'default' : 'not-allowed', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 12, color: on ? C.primary : C.text2, fontFamily: fonts.sans, fontSize: 13, fontWeight: on ? 600 : 500, opacity: on ? 1 : 0.5 }}>
            <Ico size={18}/><span>{it.label}</span>
          </button>
        );
      })}
      <div style={{ flex: 1 }} />
      <button onClick={onLogout} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 12, color: '#CF6679', fontFamily: fonts.sans, fontSize: 13, borderRadius: 10 }}>
        Sign Out
      </button>
    </div>
  );
}

function StudentBottomNav() {
  return (
    <div style={{ flexShrink: 0, background: C.surface, borderTop: `1px solid ${C.outline}`, padding: '8px 4px 22px', display: 'flex', justifyContent: 'space-around' }}>
      {NAV_ITEMS.map(it => {
        const Ico = it.icon;
        const on = it.id === 'home';
        return (
          <button key={it.id} style={{ background: 'none', border: 'none', cursor: on ? 'default' : 'not-allowed', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, padding: '4px 14px', color: on ? C.secondary : C.text2, fontFamily: fonts.sans, opacity: on ? 1 : 0.5 }}>
            <Ico size={22}/>
            <span style={{ fontSize: 10, fontWeight: on ? 600 : 500 }}>{it.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function OverviewContent({ profile, attendance, schedule, upcomingEvents, loading, error }) {
  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bg }}>
        <div style={{ color: C.text2, fontFamily: fonts.sans, fontSize: 14 }}>Loading your dashboard…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bg }}>
        <div style={{ textAlign: 'center', color: C.text2, fontFamily: fonts.sans, padding: 32 }}>
          <div style={{ fontSize: 16, color: '#CF6679', marginBottom: 8 }}>Could not load dashboard</div>
          <div style={{ fontSize: 13 }}>{error}</div>
        </div>
      </div>
    );
  }

  const attendancePct = attendance?.total > 0
    ? Math.round((attendance.present / attendance.total) * 100)
    : 0;

  return (
    <div style={{ flex: 1, overflowY: 'auto', background: C.bg, padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Greeting */}
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: C.text, fontFamily: fonts.sans }}>
          Hello, {profile?.name ?? 'Student'} 👋
        </div>
        <div style={{ fontSize: 13, color: C.text2, marginTop: 4, fontFamily: fonts.sans }}>
          {attendance?.month ?? ''}
        </div>
      </div>

      {/* Attendance card */}
      <div style={{ background: C.surface, borderRadius: 16, padding: '20px 24px', border: `1px solid ${C.outline}` }}>
        <div style={{ fontSize: 12, color: C.text2, textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: fonts.sans, marginBottom: 8 }}>
          Attendance this month
        </div>
        <div style={{ fontSize: 36, fontWeight: 800, color: attendancePct >= 75 ? C.secondary : '#CF6679', fontFamily: fonts.sans }}>
          {attendancePct}%
        </div>
        <div style={{ fontSize: 13, color: C.text2, fontFamily: fonts.sans, marginTop: 4 }}>
          {attendance?.present ?? 0} present out of {attendance?.total ?? 0} sessions
        </div>
      </div>

      {/* Today's schedule */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, fontFamily: fonts.sans, marginBottom: 12 }}>
          Today's classes
        </div>
        {(schedule ?? []).length === 0 ? (
          <div style={{ fontSize: 13, color: C.text2, fontFamily: fonts.sans }}>No classes scheduled today.</div>
        ) : (
          (schedule ?? []).map(s => (
            <div key={s.id} style={{ background: C.surface, borderRadius: 12, padding: '12px 16px', marginBottom: 8, border: `1px solid ${C.outline}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.text, fontFamily: fonts.sans }}>{s.subject}</div>
                <div style={{ fontSize: 12, color: C.text2, fontFamily: fonts.sans }}>{s.batchName} · {s.topic}</div>
              </div>
              <div style={{ fontSize: 12, color: C.text2, fontFamily: fonts.sans }}>{s.time}</div>
            </div>
          ))
        )}
      </div>

      {/* Upcoming events */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: C.text, fontFamily: fonts.sans, marginBottom: 12 }}>
          Upcoming
        </div>
        {(upcomingEvents ?? []).length === 0 ? (
          <div style={{ fontSize: 13, color: C.text2, fontFamily: fonts.sans }}>No upcoming classes found.</div>
        ) : (
          (upcomingEvents ?? []).slice(0, 5).map(e => (
            <div key={e.id} style={{ background: C.surface, borderRadius: 12, padding: '12px 16px', marginBottom: 8, border: `1px solid ${C.outline}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.text, fontFamily: fonts.sans }}>{e.label}</div>
                <div style={{ fontSize: 12, color: C.text2, fontFamily: fonts.sans }}>{e.sub} · {e.topic}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 12, color: C.primary, fontFamily: fonts.sans, fontWeight: 600 }}>{e.day}</div>
                <div style={{ fontSize: 11, color: C.text2, fontFamily: fonts.sans }}>{e.time}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default function StudentDashboard() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { signOut } = useAuth();
  const navigate = useNavigate();

  const [profile, setProfile] = useState(null);
  const [attendance, setAttendance] = useState(null);
  const [schedule, setSchedule] = useState([]);
  const [upcomingEvents, setUpcomingEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      getStudentProfile(),
      getAttendance(),
      getTodaySchedule(),
      getUpcomingEvents(),
    ])
      .then(([p, a, s, u]) => {
        setProfile(p);
        setAttendance(a);
        setSchedule(s);
        setUpcomingEvents(u);
      })
      .catch(err => setError(err.message || 'Failed to load dashboard data.'))
      .finally(() => setLoading(false));
  }, []);

  async function handleLogout() {
    await signOut();
    navigate('/onboarding');
  }

  const contentProps = { profile, attendance, schedule, upcomingEvents, loading, error };

  if (isMobile) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', background: C.bg, color: C.text }}>
        <div style={{ padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 10, borderBottom: `1px solid ${C.outline}`, background: C.bg }}>
          <div style={{ width: 24, height: 24, borderRadius: 6, background: C.secondary, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 900, color: '#1a1a1a' }}>B</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: C.text, fontFamily: fonts.sans }}>BatchBook</div>
          <div style={{ marginLeft: 4, fontSize: 10, color: C.text2, fontFamily: fonts.sans }}>Student</div>
          <button onClick={handleLogout} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#CF6679', fontFamily: fonts.sans, fontSize: 12 }}>Sign Out</button>
        </div>
        <OverviewContent {...contentProps} />
        <StudentBottomNav/>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', height: '100dvh', background: C.bg, color: C.text }}>
      <StudentSidebar name={profile?.name} onLogout={handleLogout} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ height: 64, padding: '0 28px', display: 'flex', alignItems: 'center', borderBottom: `1px solid ${C.outline}`, background: C.bg }}>
          <div style={{ fontSize: 13, color: C.text2, fontFamily: fonts.sans }}>Student · <strong style={{ color: C.text }}>Overview</strong></div>
        </div>
        <OverviewContent {...contentProps} />
      </div>
    </div>
  );
}
```

- [ ] **Step 6.4: Manual end-to-end verification**

1. Start the full stack: `make dev-d`
2. In the owner dashboard, ensure at least one student is enrolled in a batch with some recorded sessions.
3. Log in as a student/parent via `/onboarding`.
4. On the student dashboard, confirm:
   - The greeting shows the student's real name (not "Bedant Sharma")
   - The attendance percentage is a real number from the DB (not always 19/23)
   - Today's schedule shows real sessions (or "No classes scheduled today" if none exist)
5. Open DevTools Network tab — confirm calls to `/student/me/attendance`, `/student/me/upcoming-events`, and `/student/me/schedule` return 200.

- [ ] **Step 6.5: Commit**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git add src/services/dashboardService.js src/components/student/StudentDashboard.jsx
git commit -m "feat: wire student dashboard to real backend APIs (Task 0.3)"
```

- [ ] **Step 6.6: Push and open PR**

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
git push origin master
```

Then open a PR in the `BatchBook` parent repo to bump the submodule pointer:
```bash
cd ~/PycharmProjects/BatchBook
git add batchbookui
git commit -m "chore: bump batchbookui to Phase 0 stabilization (Tasks 0.1–0.3)"
git push origin master
```

---

## Task 7: Roadmap corrections

**Files:**
- Modify: `BatchBook/BATCHBOOK_ROADMAP.md`

- [ ] **Step 7.1: Update the "Two Repos" status line**

Find: `| Backend API | ... | **Phase 1–4 + 6 complete. 221 tests passing.** |`

Replace the Status cell for Backend with:
`**Phases 1–4 + 6 INTEGRATED (221 tests). Phase 0 in progress.**`

Replace the Status cell for Frontend with:
`**Owner dashboard fully integrated. Student dashboard wired in Phase 0. Teacher dashboard stub (deferred).**`

- [ ] **Step 7.2: Add "Known Integration Gaps" block to "Frontend — What Is Missing"**

After the existing bullet points in "Frontend — What Is Missing", add:

```markdown
### Known Integration Gaps (being fixed in Phase 0)
- **ProtectedRoute had no role enforcement** — any logged-in user could reach any dashboard by URL.
  Fix: Task 0.1 adds OwnerRoute + StudentRoute with session + role checks.
- **Owner post-login skipped institute creation** — new owner went straight to dashboard, causing API failures.
  Fix: Task 0.2 checks institute existence after OTP and routes to /owner/setup if missing.
- **Parent OTP called wrong endpoint** — PhoneOtpStep called /student/verify_otp; correct is /parent/verify_otp.
  Fix: Task 0.4 corrects the endpoint and stores the student ID for dashboard queries.
- **Student dashboard was 100% mock data on master** — PR #22 was a draft, never merged.
  Fix: Task 0.3 rewrites dashboardService.js and wires StudentDashboard.jsx to real backend.
- **Teacher option in OnboardingWizard routed to a non-functional dashboard** — teacher scope is deferred.
  Fix: Teacher option is disabled with a "Coming soon" tooltip.
```

- [ ] **Step 7.3: Add Phase 0 section before Phase 1**

Insert the following complete section immediately before `## PHASE 1`:

````markdown
---

## PHASE 0 — Integration Stabilization ⬜ NOT-STARTED

**What we're doing:** Fixing three integration gaps that were left when features were built in isolation. Nothing new is being built — we are making what already exists actually work together end-to-end.

**The agent MUST complete all Phase 0 tasks before picking any Phase 1–6 task.**

---

### Task 0.1 — Frontend: Role-aware routing ⬜ NOT-STARTED

**Why:** ProtectedRoute only checks session existence. Any logged-in user can reach any dashboard URL by typing it directly. This is a security and UX bug.

- [ ] Update `AuthContext.jsx`: expose `role` (read from localStorage `bb_role`); clear on signOut
- [ ] Create `OwnerRoute.jsx`: session + `role === 'owner'` required; else → `/phone-login`
- [ ] Create `StudentRoute.jsx`: session + `role === 'student'` required; else → `/onboarding`
- [ ] Update `OtpVerification.jsx`: after setSession, stamp `localStorage.setItem('bb_role', 'owner')`
- [ ] Update `PhoneOtpStep.jsx`: call `/parent/verify_otp` (not `/student/verify_otp`); stamp `bb_role = 'student'` and `bb_student_id = children[0].id`
- [ ] Update `RoleStep.jsx`: disable teacher option with "Coming soon" tooltip
- [ ] Update `App.jsx`: `/owner/*` → OwnerRoute, `/dashboard/student` → StudentRoute, `/dashboard/teacher` → static message

**Verified by:** Owner logs in → cannot access `/dashboard/student` (redirected). Student logs in → cannot access `/owner/dashboard` (redirected). Teacher card in onboarding is disabled.

---

### Task 0.2 — Frontend: Owner setup gate ⬜ NOT-STARTED

**Why:** A new owner (no institute yet) who completes OTP is sent directly to `/owner/dashboard`. Every API call that needs `institute_id` will silently fail.

- [ ] Update `OtpVerification.jsx`: after setSession and role stamp, call `GET /owner/institute`. Navigate to `/owner/setup` on 404, `/owner/dashboard` on 200.

**Verified by:** New owner account → OTP → `/owner/setup` page appears. Existing owner → OTP → `/owner/dashboard` directly.

---

### Task 0.3 — Backend + Frontend: Student dashboard live data ⬜ NOT-STARTED

**Why:** `dashboardService.js` on master is 100% hardcoded mock data. The student dashboard shows fake numbers for every student.

**Backend is already done** — `student_dashboard_route.py` is implemented and registered. No backend changes needed.

- [ ] Evaluate PR #22: if it applies cleanly to master, merge it; otherwise close it and proceed
- [ ] Rewrite `dashboardService.js` to call `/parent/me`, `/student/me/attendance`, `/student/me/schedule`, `/student/me/upcoming-events` via `api.js`
- [ ] Replace `PlaceholderContent` in `StudentDashboard.jsx` with real data display (attendance %, today's schedule, upcoming events)
- [ ] Verify: student logs in → attendance shows real DB numbers, not always "19/23"

> **Note:** Task 0.3 covers the same work as Phase 5 (Tasks 5.1 + 5.2). Mark Phase 5 Tasks 5.1 and 5.2 as ✅ INTEGRATED once Task 0.3 is verified.

````

- [ ] **Step 7.4: Update the Roadmap Overview table**

Replace the current status column:

```markdown
| Phase | Goal | Status |
|-------|------|--------|
| **0** | Integration stabilization — role routing, setup gate, student live data | ⬜ NOT-STARTED |
| **1** | Foundation: fix auth, create Owner model, basic owner dashboard shell | ✅ INTEGRATED |
| **2** | Core data: Batch + Enrollment, student management UI | ✅ INTEGRATED |
| **3** | Fee Management MVP | 🟡 PARTIAL — 3.1 ✅ 3.2 ✅ 3.3 ✅ 3.5 ✅ · 3.4 🚫 BLOCKED (WATI) |
| **4** | Attendance + WhatsApp parent alerts | 🟡 PARTIAL — 4.1 ✅ 4.3 ✅ 4.4 ✅ · 4.2 🚫 BLOCKED (WATI) |
| **5** | Connect student app to real backend | ⬜ NOT-STARTED (covered by Phase 0.3) |
| **6** | Polish, tests, performance tracker | 🟡 PARTIAL — 6.1 ✅ 6.2 ✅ 6.4 ✅ · 6.3 🔧 PARTIAL |
```

- [ ] **Step 7.5: Add Definition of INTEGRATED block**

Add this section at the very bottom of `BATCHBOOK_ROADMAP.md`, before "How to Run the Projects":

````markdown
---

## Definition of INTEGRATED (for agentic workers)

A task is only marked ✅ INTEGRATED when ALL four conditions are true:

1. **PR merged to master** — not open, not draft. Actually merged.
2. **Tests pass** — `uv run pytest -v` shows zero failures after the merge.
3. **Feature manually verified:**
   - Backend task: at least one real curl/httpie request hit the endpoint and returned expected data. Include the command + output in the PR description.
   - Frontend task: describe what a user sees when the feature works correctly (e.g. "Owner with no institute → /owner/setup page appears after OTP. Existing owner → dashboard.")
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
````

- [ ] **Step 7.6: Verify roadmap renders correctly**

Open `BATCHBOOK_ROADMAP.md` in a Markdown preview. Confirm:
- Phase 0 section appears before Phase 1
- Overview table has 7 rows (Phase 0 through 6)
- "Definition of INTEGRATED" block is at the bottom

- [ ] **Step 7.7: Run tests one final time**

```bash
cd ~/PycharmProjects/BatchBook
uv run pytest -q
# Expected: 221 tests pass (no regressions — we made no backend changes)
```

- [ ] **Step 7.8: Commit roadmap**

```bash
cd ~/PycharmProjects/BatchBook
git add BATCHBOOK_ROADMAP.md
git commit -m "docs: add Phase 0 tasks, status taxonomy, honest phase statuses, agent pre-flight protocol"
```

---

## Post-completion checklist

After all 7 tasks are committed and verified:

- [ ] Confirm `bb_role = 'owner'` is set after owner OTP and `bb_role = 'student'` after parent OTP (check DevTools → Application → Local Storage)
- [ ] Confirm owner cannot access `/dashboard/student` and student cannot access `/owner/dashboard`
- [ ] Confirm new owner is routed to `/owner/setup` after OTP
- [ ] Confirm student dashboard shows real DB numbers (not mock "19/23")
- [ ] Confirm `uv run pytest -q` still reports 221 tests passing
- [ ] Update Phase 0 tasks in roadmap:
  - Task 0.1 → ✅ INTEGRATED with "Verified by: role-based redirect confirmed in browser"
  - Task 0.2 → ✅ INTEGRATED with "Verified by: new owner routed to /owner/setup after OTP"
  - Task 0.3 → ✅ INTEGRATED with "Verified by: student dashboard shows real attendance from DB"
  - Phase 5 Tasks 5.1 and 5.2 → ✅ INTEGRATED (same work, covered by Task 0.3)
