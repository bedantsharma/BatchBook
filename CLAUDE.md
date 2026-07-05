<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **BatchBook** (4441 symbols, 7367 relationships, 90 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/BatchBook/context` | Codebase overview, check index freshness |
| `gitnexus://repo/BatchBook/clusters` | All functional areas |
| `gitnexus://repo/BatchBook/processes` | All execution flows |
| `gitnexus://repo/BatchBook/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

---

# BatchBook — Full Project Reference

> **What is BatchBook?** A vertical SaaS for India's small coaching institutes (tuition centers, 30–300 students). Owners manage students, batches, fees, and attendance. Students see their schedule, attendance, and fee status. Target customer: solo maths/science teacher in Gurugram/Jaipur/Lucknow who runs admin on WhatsApp and paper registers.

---

## Tooling Rules

- **Package manager: `uv`** — ALWAYS use `uv add <pkg>` and `uv run <cmd>` instead of `pip` or `python` directly.
- **Linter/formatter: `ruff`** — line length 100, Python 3.14 target. Auto-fix is on. Alembic folder is excluded.
- **Test runner: `pytest`** — async mode is `auto`. Tests live in `tests/`. Run with `uv run pytest`.
- **Python version: 3.14** (`.python-version` enforced).

---

## Repo Layout

use the gitnexus commands to search for keyword in the repo and if the gitnexus index is stale then reindex it.


---

## Data Models

All the models live int he /models folder feel free to look there if needed



## Service Layer Patterns

Each service follows this pattern:
- **Constructor** creates a repository instance (`self.owner_repo = OwnerRepository()`)
- **`verify_otp(...)`** calls Supabase, gets `teacher_id`/`user_id`, calls `get_or_create_after_otp` to upsert the DB record, returns `(access_token, refresh_token, aud, uuid)`
- **`get_current_*_id(supabase, authorization)`** delegates to `auth_service.get_current_user_id` (shared, no duplication)
- Services are provided via FastAPI `Depends` through a `get_*_service()` factory function

---

## Database

- **Database:** PostgreSQL hosted on Supabase
- **ORM:** SQLAlchemy 2.0 async (`AsyncSession`, `async_sessionmaker`, `create_async_engine`)
- **Driver:** `asyncpg` (async) + `psycopg2-binary` (sync fallback/alembic)
- **Migrations:** Alembic autogenerate
  ```bash
  # Create a new migration (always from BatchBook/ root)
  uv run alembic revision --autogenerate -m "describe your change"
  uv run alembic upgrade head
  ```
- **Test DB:** `aiosqlite` in-memory SQLite for tests (injected via dependency override in `conftest.py`)
- **`db/base.py`** — must import all models before Alembic can autogenerate migrations; `models/__init__.py` handles this

---

## CORS

Configured in `app.py`. Currently allowed origins:
- `http://localhost:5173`, `5174`, `5175` (Vite dev server)
- An ngrok URL (for mobile testing on phone)

Add new origins here when deploying or testing from a different port.

---

## Running (Docker — preferred)

Everything is Dockerised. Use the Makefile from the project root:

```bash
make dev          # start frontend + backend with hot-reload (foreground)
make dev-d        # same but detached (background)
make prod         # production build, detached (nginx + 2 uvicorn workers)
make down         # stop all containers

make frontend     # rebuild & restart ONLY the frontend (dev by default)
make backend      # rebuild & restart ONLY the backend  (dev by default)
make frontend MODE=prod   # same but targeting prod compose file
make backend  MODE=prod

make logs         # tail all logs (dev stack)
make logs-f       # tail frontend only
make logs-b       # tail backend only

make build        # build all images without starting
make clean        # stop + remove images + anonymous volumes
make ps           # show running containers
make help         # print all targets
```

**Dev URLs:** frontend → `http://localhost:5173` · backend → `http://localhost:8000/docs`
**Prod URLs:** frontend → `http://localhost:80` · backend → `http://localhost:8000`

### Docker file map

| File | Purpose |
|------|---------|
| `Dockerfile` | Backend multi-stage image (`dev` + `prod` targets) |
| `.dockerignore` | Excludes `.venv`, `__pycache__`, `.env`, `batchbookui/` |
| `batchbookui/Dockerfile` | Frontend multi-stage image (`dev` + `prod` targets) |
| `batchbookui/nginx.conf` | Prod nginx: SPA routing + proxy `/student/*` `/owner/*` to backend |
| `batchbookui/.dockerignore` | Excludes `node_modules/`, `dist/` |
| `docker-compose.dev.yml` | Dev stack: volume-mounted source, Vite HMR, uvicorn `--reload` |
| `docker-compose.prod.yml` | Prod stack: baked images, 2 uvicorn workers, nginx |
| `Makefile` | All `make` targets; `MODE=dev` default, override with `MODE=prod` |

### How hot-reload works in dev

- **Backend:** host `BatchBook/` is volume-mounted to `/app` inside the container; uvicorn `--reload` watches for changes. `.venv` is protected by an anonymous volume so the host mount never overwrites the container's virtualenv.
- **Frontend:** host `batchbookui/` is volume-mounted; Vite HMR detects changes and pushes updates to the browser. `node_modules/` is protected by an anonymous volume for the same reason.

---

## Production Deployment (Render.com)

Backend deploys to **Render.com** as a single Docker web service. Frontend stays on **Vercel** (already deployed at `batchbookui.vercel.app`, custom domain `batchbook.in` pending DNS). Domain: **batchbook.in** (Namecheap).

**Render does not read `docker-compose.prod.yml`** — it builds exactly one Dockerfile per service. Point it at:
- Dockerfile path: `./Dockerfile` (repo root — backend only)
- Build context: `.` (repo root)
- No `--target` flag needed: `prod` is the last stage in the Dockerfile, so a plain build already produces it
- `.dockerignore` excludes `batchbookui/` from the build context, so the backend image can never accidentally pull in frontend code — there's no risk of Render spinning up both services from this single Dockerfile

**Differences from the local Docker Compose stack — must configure these on Render:**

1. **Port** — Render injects `$PORT` and routes traffic to it. The Dockerfile's prod CMD hardcodes `uvicorn --port 8000`. Set an env var `PORT=8000` in the Render dashboard to match (no Dockerfile change needed).
2. **Migration guard is skipped** — `alembic-check` (in `docker-compose.prod.yml`) is a separate one-shot compose service; Render never runs it since it only builds the single backend Dockerfile. Migrations must be applied manually: `uv run alembic upgrade head` against the prod `DATABASE_URL`, run before/after each deploy with a schema change (or via Render's Pre-Deploy Command field, if available on the plan).
3. **`.env` is not read** — Render ignores `env_file: .env` from compose. Set every var individually in the Render dashboard: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `PROJECT_NAME`, `PORT`.
4. **CORS** — production frontend origins (`https://batchbookui.vercel.app`, `https://batchbook.in`, `https://www.batchbook.in`) must already be in `allow_origins` in `app.py` *before* first deploy, to avoid a redeploy just for a CORS fix.

**Custom domain:** add `api.batchbook.in` in Render → Settings → Custom Domain. Render gives you a CNAME target — add that as a CNAME record for the `api` subdomain in Namecheap Advanced DNS. Same pattern for `batchbook.in` / `www.batchbook.in` pointed at Vercel (Vercel's domain settings page shows the exact A/CNAME records to add).

## Running the Backend (without Docker)

```bash
cd ~/PycharmProjects/BatchBook
uv run uvicorn app:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
# ReDoc:      http://localhost:8000/redoc
```

## Running Tests

```bash
cd ~/PycharmProjects/BatchBook
uv run pytest -v
```

---

## Environment Variables (`BatchBook/.env`)

```
PROJECT_NAME=BatchBook
DATABASE_URL=XXXXX
SUPABASE_URL=XXXXX
SUPABASE_KEY=XXXXX
RAZORPAY_KEY_ID=XXXXX
RAZORPAY_KEY_SECRET=XXXXX
META_WHATSAPP_TOKEN=XXXXX
META_WHATSAPP_PHONE_NUMBER_ID=XXXXX
WABA_ID=XXXXX
RAZORPAY_ENCRYPTION_KEY=XXXXX
FRONTEND_BASE_URL=XXXXX
ENABLE_SCHEDULER=XXXXX
ADMIN_BACKFILL_SECRET=XXXXX
```

All config is via `config.py` → `Settings(BaseSettings)`. Add new vars there AND in `.env`.

---

## Quick File Reference

| What you want to change | File |
|-------------------------|------|
| Add a new API endpoint | `routes/<domain>_route.py` |
| Add business logic | `services/<domain>_service.py` |
| Add a DB query | `repositories/<domain>_repository.py` |
| Add/change a DB table | `models/<name>_base.py` → run alembic |
| Add a request body schema | `routes/requests/<name>_request.py` |
| Add a response schema | `routes/responses/<name>_response.py` |
| Add an env variable | `config.py` (Settings class) + `.env` |
| Register a new router | `app.py` → `app.include_router(...)` |

---

---

# batchbookui — Frontend Submodule

## ⚠️ Git Submodule Rules — READ BEFORE TOUCHING `batchbookui/`

`batchbookui/` is a **git submodule**, not a regular folder. It is a fully independent git repo (`github.com/bedantsharma/batchbookui`) that lives inside BatchBook. BatchBook only stores a pointer (a specific commit SHA) — it does **not** own or track the UI files directly.

### Claude: How to handle commits here

**Rule 1 — Two separate commits, two separate repos.**
Changes inside `batchbookui/` must be committed and pushed from *within* that folder using its own git identity. A commit to `BatchBook/` will never include the UI file changes — only the submodule pointer update.

**Rule 2 — Always commit in this order:**
```bash
# Step 1: commit the UI changes inside the submodule
cd batchbookui/
git add .
git commit -m "feat: your ui change"
git push origin <branch>

# Step 2: update the pointer in the parent repo
cd ..
git add batchbookui        # stages the new SHA pointer, not the files
git commit -m "chore: bump batchbookui submodule to latest"
git push origin master
```

**Rule 3 — Never `git add batchbookui/` with a trailing slash.**
`git add batchbookui` (no slash) stages the pointer update. `git add batchbookui/` tries to stage the files — this is wrong and will cause errors.

**Rule 4 — Check which repo you're in before committing.**
Run `git remote -v` if unsure. The BatchBook remote points to `BatchBook.git`; the batchbookui remote points to `batchbookui.git`.

**Rule 5 — If only changing frontend files, do NOT commit to the parent repo** unless you also want to advance the submodule pointer. It is perfectly fine to commit + push inside `batchbookui/` without touching the parent repo.

| Task | Command |
|------|---------|
| Clone BatchBook fresh (includes submodule) | `git clone --recurse-submodules git@github.com:bedantsharma/BatchBook.git` |
| Init submodule after cloning without `--recurse` | `git submodule update --init` |
| Pull latest UI into BatchBook | `cd batchbookui && git pull` → `cd .. && git add batchbookui && git commit` |

---

## Frontend Stack

| Tool | Version | Purpose |
|------|---------|---------|
| React | 19 | UI framework |
| Vite | 8 | Build tool / dev server (port 5173) |
| React Router DOM | 7 | Client-side routing |
| MUI (Material UI) | 9 | Component library (Material 3 dark theme) |
| Emotion | 11 | CSS-in-JS (MUI dependency) |
| Lucide React | latest | Icons |
| Tailwind CSS | via `tw-animate-css` | Utility classes |
| Firebase | 12 | ⚠️ BEING REMOVED — currently handles phone OTP (see Phase 1.5) |

---

## Frontend Repo Layout (`batchbookui/`)

```
batchbookui/
├── index.html                      ← Vite entry HTML
├── package.json                    ← npm scripts: dev, build, lint, preview
├── jsconfig.json                   ← JS paths config
├── components.json                 ← shadcn/ui config (class-variance-authority present)
├── eslint.config.js                ← ESLint flat config
├── public/
│   ├── favicon.svg
│   └── icons.svg                   ← SVG icon sprite
├── src/
│   ├── main.jsx                    ← React entry point (mounts <App />)
│   ├── App.jsx                     ← Router + MUI ThemeProvider (dark Material 3 theme)
│   ├── firebaseconfig.ts           ← ⚠️ Firebase init — DELETE in Phase 1.5
│   ├── assets/
│   │   └── hero.png
│   ├── lib/
│   │   └── utils.js                ← cn() helper (clsx + tailwind-merge)
│   ├── components/                 ← Shared/page components (currently flat, not yet split into pages/)
│   │   ├── PhoneLogin.jsx          ← Phone number input → Firebase signInWithPhoneNumber (TO BE REPLACED with Supabase)
│   │   ├── OtpVerification.jsx     ← 6-digit OTP input → Firebase confirmationResult.confirm (TO BE REPLACED)
│   │   └── Dashboard.jsx           ← Student dashboard (3 tabs: Home, Schedule, Profile) — ALL MOCK DATA
│   └── services/
│       └── dashboardService.js     ← Mock data service (all TODOs — see Phase 5)
└── batchbook-design-system/        ← Design tokens, fonts, color previews (read-only reference)
    └── project/
        ├── colors_and_type.css     ← CSS variables for colors + typography
        ├── fonts/                  ← JetBrains Mono TTF files
        ├── assets/                 ← Logo, icons, hero image
        ├── preview/                ← HTML previews of design tokens (buttons, cards, OTP, etc.)
        └── ui_kits/batchbook-app/ ← UI kit reference
```

---

## Frontend Routes (current)

| Path | Component | Status |
|------|-----------|--------|
| `/` | `PhoneLogin` | Works (Firebase) — to be migrated to Supabase |
| `/phone-login` | `PhoneLogin` | Same as above |
| `/otp-verification` | `OtpVerification` | Works (Firebase) — to be migrated |
| `/dashboard` | `Dashboard` | Works with mock data only |

**Planned routes (Phase 1.6):**
- `/owner/setup` — first-time institute setup
- `/owner/dashboard` — owner main app (sidebar layout)

---

## Frontend Theme

Dark Material 3 theme defined in `App.jsx`:
- **Primary:** `#BB86FC` (purple)
- **Secondary:** `#03DAC6` (cyan/teal)
- **Background:** `#121212` / `#1E1E1E`
- **Font:** `DM Sans` (typography) + `JetBrains Mono` (monospace, from design system)
- **Border radius:** Cards 16px, Buttons 16px, TextFields 12px

---

## Dashboard Mock Data (`services/dashboardService.js`)

All functions return hardcoded data with a 300ms simulated delay. Every function has a `// TODO` comment showing the real API endpoint to wire up in Phase 5:

| Function | Future endpoint |
|----------|----------------|
| `getStudentProfile()` | `GET /student/me` |
| `getAttendance()` | `GET /student/me/attendance?month=YYYY-MM` |
| `getUpcomingEvents()` | `GET /student/me/upcoming-events?limit=10` |
| `getTodaySchedule()` | `GET /student/me/schedule?date=YYYY-MM-DD` |
| `getUnreadNotificationCount()` | `GET /student/me/notifications/unread-count` |

---

## Running the Frontend

```bash
cd ~/PycharmProjects/BatchBook/batchbookui
# OR the standalone repo:
cd ~/WebstormProjects/batchbookui

npm run dev      # http://localhost:5173
npm run build    # production build
npm run lint     # ESLint check
```

---

## Frontend Environment Variables (`batchbookui/.env`)

```
VITE_SUPABASE_URL=https://[project-id].supabase.co    # Add in Phase 1.5
VITE_SUPABASE_ANON_KEY=eyJhbGci...                    # Add in Phase 1.5
```

> The `.env` file is gitignored. Get `SUPABASE_ANON_KEY` from Supabase Dashboard → Settings → API.

---

---

# Project-Wide Architecture

```
[Owner's Browser]              [Student/Parent's Phone Browser]
       |                                |
  /owner/* routes               /student/* routes
       |                                |
       └──────────── React App ─────────┘
               (batchbookui, port 5173)
                         |
               src/services/api.js     ← axios instance; auto-attaches JWT (Phase 1.6)
                         |
             FastAPI Backend (port 8000)
                         |
               ┌─────────┴──────────┐
          Supabase Auth         PostgreSQL DB
          (OTP + JWT)      (SQLAlchemy + Alembic)
```

## Planned DB Relationships (full schema, for future phases)

```
Owner ──────────── Institute (1:1)
Institute ──────── Batch (1:many)
Institute ──────── Teacher (1:many — teachers hired by owner)
Batch ───────────  BatchTeacher (many:many join table)
Batch ───────────  Enrollment (1:many)
Batch ───────────  FeeStructure (1:1)
Batch ───────────  ClassSession (1:many)
Parent ──────────  Student (1:many — parent sees all their children)
Student ─────────  Enrollment (1:many — student in multiple batches)
Enrollment ──────  FeeRecord (1:many — one per month)
ClassSession ────  Attendance (1:many — one per enrolled student per session)
Batch ───────────  TestScore (via Enrollment — Phase 6)
```

**Key design decisions:**
- `Parent` holds phone + Supabase auth. The "student app" is actually a parent app. Siblings share one parent account.
- `due_day` lives on `Enrollment` (not `FeeStructure`) — students joining mid-month get their own payment cycle.
- `Batch.status` lifecycle: `ACTIVE → CLOSING` (auto when `end_date` passes) `→ ARCHIVED` (manual, only when all fees settled).

---

## Roadmap Phase Summary

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | CORS + Owner model + Firebase→Supabase migration + owner dashboard shell | In progress (Tasks 1.1–1.2 done, 1.3–1.6 pending) |
| 2 | Batch + Enrollment models + frontend batch management UI | Not started |
| 3 | Fee management (FeeStructure, FeeRecord, Razorpay links, WATI WhatsApp) | Not started |
| 4 | Attendance (ClassSession, Attendance, absence WhatsApp alerts) | Not started |
| 5 | Connect student dashboard to real backend (replace all mock data) | Not started |
| 6 | Tests, performance tracker (test scores), error handling polish | Not started |

See `BATCHBOOK_ROADMAP.md` for the full detailed task breakdown with explanations.
