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