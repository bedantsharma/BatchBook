# Task F.8 Tier 2 Site Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let BatchBook generate a real, crawler-visible business website on a wildcard subdomain (`{slug}.batchbook.in`) for owners who won't self-serve a Tier 1 site, unblocking their Razorpay live-key approval.

**Architecture:** Two independent pieces. (1) The existing `BatchBook` FastAPI backend gets new `Institute` columns, an unauthenticated `GET /public/institute/{slug}` read endpoint, and an admin-secret-gated `POST /admin/institute/{institute_id}/generate-site` write endpoint. (2) A brand-new sibling repo `batchbook-site-generator` — a single Vercel Node.js serverless function that reads the `Host` header, calls the public endpoint, and renders server-side HTML with a color-scheme-driven `<style>` block. No framework in either the endpoint or the generator; both follow this codebase's existing minimal-plumbing patterns (see `routes/admin_route.py`, `routes/webhook_route.py`).

**Tech Stack:** Backend: FastAPI, SQLAlchemy 2.0 async, Alembic, pytest (existing stack, no new deps). Generator: plain Node.js on Vercel's serverless runtime, no npm dependencies.

## Global Constraints

- Package manager for the backend is `uv` — always `uv add` / `uv run`, never bare `pip`/`python`. (CLAUDE.md)
- Backend line length 100, ruff auto-fix on, Python 3.14 target. (CLAUDE.md)
- Test runner is `pytest`, async mode `auto`, tests live in `tests/`. Run with `uv run pytest`. (CLAUDE.md)
- **Before modifying any existing function/class/method in the backend**, run `gitnexus_impact({target: "<symbolName>", direction: "upstream"})` and report the blast radius before proceeding; stop and warn if it returns HIGH/CRITICAL risk. (CLAUDE.md — this project is GitNexus-indexed)
- **Before committing any backend change**, run `gitnexus_detect_changes()` and confirm only the expected symbols/flows are affected.
- Never rename existing symbols via find-and-replace — not needed in this plan (no renames), but if a step is tempted to, use `gitnexus_rename` instead.
- `color_scheme` preset table (name → primary/accent/background hex) must stay byte-identical between the Python backend (`services/site_color_presets.py`) and the Node generator (`api/colorPresets.js`) — both are written out verbatim in this plan; do not paraphrase or reorder them.
- The 10 preset names, in order (index 0–9): `indigo, teal, maroon, forest, slate, amber, plum, ocean, terracotta, charcoal-gold`. Index order matters — it's what `hash(slug) % 10` indexes into.
- Spec of record: `docs/superpowers/specs/2026-07-06-f8-tier2-site-generator-design.md`. If any task here seems to contradict it, the spec wins — stop and flag it rather than guessing.

---

## File Structure

**BatchBook repo (backend):**
- Modify: `models/institute_base.py` — add 7 nullable columns
- Create: `alembic/versions/d4e5f6a7b8c9_institute_public_site_fields.py` — migration
- Modify: `repositories/institute_repository.py` — add `get_by_slug`
- Create: `services/site_color_presets.py` — preset table + `resolve_color_scheme(slug, requested)`
- Modify: `services/institute_service.py` — add `get_public_by_slug`, `generate_site`
- Create: `routes/responses/public_institute_response.py` — response schema
- Create: `routes/public_route.py` — `GET /public/institute/{slug}`
- Create: `routes/requests/generate_site_request.py` — request schema
- Modify: `routes/admin_route.py` — add `POST /admin/institute/{institute_id}/generate-site`
- Modify: `app.py` — register `public_router`
- Create: `tests/test_site_color_presets.py`
- Modify: `tests/test_institute_repository.py` — `get_by_slug` tests
- Modify: `tests/test_institute_service.py` — `get_public_by_slug`, `generate_site` tests
- Create: `tests/test_public_routes.py`
- Modify: `tests/test_admin_routes.py` — `generate-site` tests

**New repo (`../batchbook-site-generator`, sibling to `BatchBook/`):**
- Create: `package.json`
- Create: `vercel.json`
- Create: `api/colorPresets.js`
- Create: `api/render.js`
- Create: `api/[[...slug]].js`
- Create: `.env.example`
- Create: `README.md`
- Create: `test/render.test.js` (Node's built-in test runner — no dependency needed)

**Docs:**
- Modify: `PhaseF.md` — check off the Task F.8 checklist items this plan completes
- Modify: `BATCHBOOK_ROADMAP_V2.md` — update Phase F status line

---

### Task 1: `Institute` model fields + migration

**Files:**
- Modify: `models/institute_base.py`
- Create: `alembic/versions/d4e5f6a7b8c9_institute_public_site_fields.py`
- Modify: `tests/test_institute_repository.py`

**Interfaces:**
- Produces: 7 new nullable columns on `InstituteSchema` — `slug: str | None` (unique, indexed), `address: str | None`, `phone_public: str | None`, `email_public: str | None`, `description: str | None`, `course_fee_display: str | None`, `color_scheme: str | None`. All later tasks read/write these by these exact names.

- [ ] **Step 1: Run impact analysis on `InstituteSchema` before editing**

Run: `gitnexus_impact({target: "InstituteSchema", direction: "upstream"})` (or the CLI/MCP equivalent available in your session). Report the blast radius (direct callers, affected flows, risk level). Adding purely-nullable columns to an existing table is low risk, but confirm no HIGH/CRITICAL warning before proceeding. If GitNexus reports the index is stale, run `npx gitnexus analyze` first.

- [ ] **Step 2: Add the columns**

In `models/institute_base.py`, add after the existing `razorpay_status` column (before `created_at`):

```python
    slug = Column(String, nullable=True, unique=True, index=True)
    address = Column(String, nullable=True)
    phone_public = Column(String, nullable=True)
    email_public = Column(String, nullable=True)
    description = Column(String, nullable=True)
    course_fee_display = Column(String, nullable=True)
    color_scheme = Column(String, nullable=True)
```

- [ ] **Step 3: Write a failing repository test for the new fields**

Add to `tests/test_institute_repository.py`, in the `# --- update ---` section (new section after it, `# --- public site fields ---`):

```python
# --- public site fields ---

async def test_create_institute_allows_public_site_fields_unset(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    created = await repo.create(db_session, _institute(owner.id, "Plain Institute", "Delhi", "PLAN0001"))

    assert created.slug is None
    assert created.color_scheme is None


async def test_update_sets_public_site_fields(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    institute = await repo.create(db_session, _institute(owner.id, "Site Institute", "Jaipur", "SITE0001"))

    updated = await repo.update(
        db_session,
        institute,
        {
            "slug": "site-institute",
            "address": "123 MG Road, Jaipur",
            "phone_public": "9999999999",
            "email_public": "contact@example.com",
            "description": "Maths and Science tuition for Class 9-12",
            "course_fee_display": "Rs 3000/month",
            "color_scheme": "teal",
        },
    )

    assert updated.slug == "site-institute"
    assert updated.color_scheme == "teal"
    assert updated.course_fee_display == "Rs 3000/month"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/test_institute_repository.py -v -k public_site_fields`
Expected: FAIL — `AttributeError` or similar, since the columns don't exist on the model yet (if Step 2 wasn't done yet) — since Step 2 already happened above, this should actually now PASS. Run it anyway to confirm the model change is what makes it pass (i.e., temporarily comment out the 7 lines from Step 2, confirm FAIL, then restore them).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_institute_repository.py -v`
Expected: PASS — all existing institute repository tests plus the 2 new ones.

- [ ] **Step 6: Generate the Alembic migration**

Create `alembic/versions/d4e5f6a7b8c9_institute_public_site_fields.py`:

```python
"""institute public site fields (Task F.8 Tier 2)

Revision ID: d4e5f6a7b8c9
Revises: a24386059615
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "a24386059615"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Institute", sa.Column("slug", sa.String(), nullable=True))
    op.create_unique_constraint("uq_institute_slug", "Institute", ["slug"])
    op.create_index("ix_institute_slug", "Institute", ["slug"])
    op.add_column("Institute", sa.Column("address", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("phone_public", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("email_public", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("description", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("course_fee_display", sa.String(), nullable=True))
    op.add_column("Institute", sa.Column("color_scheme", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("Institute", "color_scheme")
    op.drop_column("Institute", "course_fee_display")
    op.drop_column("Institute", "description")
    op.drop_column("Institute", "email_public")
    op.drop_column("Institute", "phone_public")
    op.drop_column("Institute", "address")
    op.drop_index("ix_institute_slug", table_name="Institute")
    op.drop_constraint("uq_institute_slug", "Institute", type_="unique")
    op.drop_column("Institute", "slug")
```

This is hand-written (not `alembic revision --autogenerate`) because autogenerate needs a live connection to the Supabase Postgres DB to diff against (`alembic/env.py` builds its engine from `settings.database_url`), which this environment may not have network access to. It follows the exact same shape as `alembic/versions/h2i3j4k5l6m7_institute_join_code_parent_institute.py`'s `join_code` unique+index columns, minus the backfill/NOT NULL steps (not needed here since every field stays nullable forever).

- [ ] **Step 7: Verify the migration is syntactically valid**

Run: `uv run python -c "import importlib.util; spec = importlib.util.spec_from_file_location('m', 'alembic/versions/d4e5f6a7b8c9_institute_public_site_fields.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.revision, m.down_revision)"`
Expected output: `d4e5f6a7b8c9 a24386059615`

If you have network access to the real dev/staging `DATABASE_URL` in this environment, also run `uv run alembic upgrade head` and confirm it applies cleanly, then `uv run alembic downgrade -1` to confirm the downgrade also works, then `uv run alembic upgrade head` again. If you don't have DB access here, leave this for the user to run before deploying — say so explicitly in your task summary.

- [ ] **Step 8: Run gitnexus_detect_changes and the full backend test suite**

Run: `gitnexus_detect_changes()` — confirm only `InstituteSchema` and its known dependents are listed, nothing unexpected.
Run: `uv run pytest -v`
Expected: all tests pass (320+ existing plus the 2 new ones), no failures introduced.

- [ ] **Step 9: Commit**

```bash
git add models/institute_base.py alembic/versions/d4e5f6a7b8c9_institute_public_site_fields.py tests/test_institute_repository.py
git commit -m "feat: add public-site fields to Institute model (Task F.8 Tier 2)"
```

---

### Task 2: `InstituteRepository.get_by_slug`

**Files:**
- Modify: `repositories/institute_repository.py`
- Modify: `tests/test_institute_repository.py`

**Interfaces:**
- Consumes: `InstituteSchema.slug` (Task 1).
- Produces: `InstituteRepository.get_by_slug(db: AsyncSession, slug: str) -> InstituteSchema | None`. Task 4's service layer calls this by exact name.

- [ ] **Step 1: Run impact analysis on `InstituteRepository` before editing**

Run: `gitnexus_impact({target: "InstituteRepository", direction: "upstream"})`. Report blast radius — expect only `InstituteService` as a direct caller. Confirm no HIGH/CRITICAL risk before proceeding.

- [ ] **Step 2: Write the failing test**

Add to `tests/test_institute_repository.py`, in the `# --- public site fields ---` section added in Task 1:

```python
# --- get_by_slug ---

async def test_get_by_slug_returns_institute(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    institute = await repo.create(db_session, _institute(owner.id, "Slug Test", "Lucknow", "SLUG0001"))
    await repo.update(db_session, institute, {"slug": "slug-test"})

    found = await repo.get_by_slug(db_session, "slug-test")

    assert found is not None
    assert found.id == institute.id


async def test_get_by_slug_returns_none_for_unknown_slug(db_session, repo):
    result = await repo.get_by_slug(db_session, "does-not-exist")
    assert result is None


async def test_get_by_slug_returns_none_when_slug_is_null(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    await repo.create(db_session, _institute(owner.id, "No Slug", "Kanpur", "NOSL0001"))

    result = await repo.get_by_slug(db_session, "")
    assert result is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_institute_repository.py -v -k get_by_slug`
Expected: FAIL with `AttributeError: 'InstituteRepository' object has no attribute 'get_by_slug'`

- [ ] **Step 4: Implement `get_by_slug`**

In `repositories/institute_repository.py`, add after `get_by_join_code`:

```python
    async def get_by_slug(self, db: AsyncSession, slug: str) -> InstituteSchema | None:
        result = await db.execute(
            select(InstituteSchema).where(InstituteSchema.slug == slug)
        )
        return result.scalar_one_or_none()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_institute_repository.py -v`
Expected: PASS — all institute repository tests.

- [ ] **Step 6: Run gitnexus_detect_changes**

Run: `gitnexus_detect_changes()` — confirm the only new/changed symbol is `InstituteRepository.get_by_slug` plus the test file.

- [ ] **Step 7: Commit**

```bash
git add repositories/institute_repository.py tests/test_institute_repository.py
git commit -m "feat: add InstituteRepository.get_by_slug (Task F.8 Tier 2)"
```

---

### Task 3: Color-scheme presets module

**Files:**
- Create: `services/site_color_presets.py`
- Create: `tests/test_site_color_presets.py`

**Interfaces:**
- Produces:
  - `COLOR_PRESETS: dict[str, dict[str, str]]` — keys are the 10 preset names, values are `{"primary": "#...", "accent": "#...", "background": "#..."}`.
  - `PRESET_NAMES: list[str]` — the 10 names in the fixed order from Global Constraints.
  - `is_valid_color_scheme(name: str) -> bool`
  - `resolve_color_scheme(slug: str, requested: str | None) -> str` — returns `requested` if it's a valid preset name; otherwise deterministically picks `PRESET_NAMES[hash(slug) % 10]`. Raises `ValueError` if `requested` is given but not a valid preset name (callers must not silently fall back on a typo). Task 4's `generate_site` calls this by exact name and signature.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_site_color_presets.py`:

```python
"""
Tests for services/site_color_presets.py.

Symbols under test:
  Module:services/site_color_presets.py
    is_valid_color_scheme, resolve_color_scheme
"""

import pytest

from services.site_color_presets import (
    COLOR_PRESETS,
    PRESET_NAMES,
    is_valid_color_scheme,
    resolve_color_scheme,
)


def test_preset_names_match_color_presets_keys():
    assert set(PRESET_NAMES) == set(COLOR_PRESETS.keys())
    assert len(PRESET_NAMES) == 10


def test_every_preset_has_primary_accent_background():
    for name, colors in COLOR_PRESETS.items():
        assert set(colors.keys()) == {"primary", "accent", "background"}
        for hex_value in colors.values():
            assert hex_value.startswith("#")


def test_is_valid_color_scheme_true_for_known_name():
    assert is_valid_color_scheme("teal") is True


def test_is_valid_color_scheme_false_for_unknown_name():
    assert is_valid_color_scheme("neon-pink") is False


def test_resolve_color_scheme_returns_requested_when_valid():
    assert resolve_color_scheme("any-slug", "maroon") == "maroon"


def test_resolve_color_scheme_rejects_invalid_requested():
    with pytest.raises(ValueError):
        resolve_color_scheme("any-slug", "neon-pink")


def test_resolve_color_scheme_is_deterministic_for_same_slug():
    first = resolve_color_scheme("bedants-tuition", None)
    second = resolve_color_scheme("bedants-tuition", None)
    assert first == second
    assert first in PRESET_NAMES


def test_resolve_color_scheme_can_differ_across_slugs():
    results = {resolve_color_scheme(f"slug-{i}", None) for i in range(10)}
    assert len(results) > 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_site_color_presets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.site_color_presets'`

- [ ] **Step 3: Implement the module**

Create `services/site_color_presets.py`:

```python
COLOR_PRESETS: dict[str, dict[str, str]] = {
    "indigo": {"primary": "#3730A3", "accent": "#6366F1", "background": "#F5F5FF"},
    "teal": {"primary": "#0F766E", "accent": "#14B8A6", "background": "#F0FDFA"},
    "maroon": {"primary": "#9F1239", "accent": "#E11D48", "background": "#FFF1F2"},
    "forest": {"primary": "#166534", "accent": "#22C55E", "background": "#F0FDF4"},
    "slate": {"primary": "#1E293B", "accent": "#475569", "background": "#F8FAFC"},
    "amber": {"primary": "#92400E", "accent": "#F59E0B", "background": "#FFFBEB"},
    "plum": {"primary": "#6B21A8", "accent": "#A855F7", "background": "#FAF5FF"},
    "ocean": {"primary": "#075985", "accent": "#0EA5E9", "background": "#F0F9FF"},
    "terracotta": {"primary": "#9A3412", "accent": "#EA580C", "background": "#FFF7ED"},
    "charcoal-gold": {"primary": "#292524", "accent": "#CA8A04", "background": "#FAFAF9"},
}

PRESET_NAMES: list[str] = list(COLOR_PRESETS.keys())


def is_valid_color_scheme(name: str) -> bool:
    return name in COLOR_PRESETS


def resolve_color_scheme(slug: str, requested: str | None) -> str:
    """Resolve the color-scheme name to persist for a given slug.

    Raises:
        ValueError: If `requested` is given but isn't one of the fixed presets.
    """
    if requested is not None:
        if not is_valid_color_scheme(requested):
            raise ValueError(
                f"'{requested}' is not a valid color scheme — choose one of {PRESET_NAMES}"
            )
        return requested
    return PRESET_NAMES[hash(slug) % len(PRESET_NAMES)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_site_color_presets.py -v`
Expected: PASS — all 8 tests.

- [ ] **Step 5: Commit**

```bash
git add services/site_color_presets.py tests/test_site_color_presets.py
git commit -m "feat: add fixed color-scheme presets for Tier 2 sites (Task F.8)"
```

---

### Task 4: `InstituteService.get_public_by_slug` + `generate_site`

**Files:**
- Modify: `services/institute_service.py`
- Modify: `tests/test_institute_service.py`

**Interfaces:**
- Consumes: `InstituteRepository.get_by_slug` (Task 2), `InstituteRepository.get_by_id` (existing), `InstituteRepository.update` (existing), `resolve_color_scheme` / `is_valid_color_scheme` from `services.site_color_presets` (Task 3).
- Produces:
  - `InstituteService.get_public_by_slug(db, slug: str) -> InstituteSchema | None`
  - `InstituteService.generate_site(db, institute_id: int, *, slug: str, address: str, phone_public: str, email_public: str, description: str, course_fee_display: str, color_scheme: str | None = None) -> InstituteSchema` — raises `ValueError` for: unknown `institute_id`, invalid slug format, slug already taken by a *different* institute, invalid `color_scheme`. Task 5 and Task 6's routes call this by exact name and catch `ValueError`.

- [ ] **Step 1: Run impact analysis on `InstituteService` before editing**

Run: `gitnexus_impact({target: "InstituteService", direction: "upstream"})`. Report blast radius — expect callers in `routes/owner_route.py`, `routes/admin_route.py` (after Task 6), `routes/webhook_route.py`. Confirm no HIGH/CRITICAL risk; this task only *adds* methods, it doesn't change existing ones, so risk should be low.

- [ ] **Step 2: Write the failing tests**

`tests/test_institute_service.py` mocks `service.institute_repo` methods via `patch.object(..., new=AsyncMock(...))` against a bare `mock_db = AsyncMock()` fixture — it never touches a real DB session (unlike `tests/test_institute_repository.py`). Follow that exact convention. Add this section, using the file's existing `service`/`mock_db` fixtures and `_make_institute()` helper (all already defined near the top of the file):

```python
# --- get_public_by_slug ---

async def test_get_public_by_slug_returns_institute(service, mock_db):
    expected = _make_institute()
    with patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=expected)):
        result = await service.get_public_by_slug(mock_db, "test-institute")

    assert result is expected


async def test_get_public_by_slug_returns_none_for_unknown_slug(service, mock_db):
    with patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=None)):
        result = await service.get_public_by_slug(mock_db, "nope")

    assert result is None


async def test_get_public_by_slug_returns_none_for_empty_slug(service, mock_db):
    result = await service.get_public_by_slug(mock_db, "")
    assert result is None


# --- generate_site ---

async def test_generate_site_persists_all_fields(service, mock_db):
    existing = _make_institute(owner_id=4)
    updated = _make_institute(owner_id=4)
    updated.slug = "site-gen-test"
    updated.address = "1 Test Road"
    updated.color_scheme = "teal"
    update_mock = AsyncMock(return_value=updated)

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=None)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        result = await service.generate_site(
            mock_db,
            10,
            slug="site-gen-test",
            address="1 Test Road",
            phone_public="9876543210",
            email_public="hi@example.com",
            description="Chemistry tuition for Class 11-12",
            course_fee_display="Rs 3000/month",
        )

    assert result is updated
    update_mock.assert_called_once()
    call_args = update_mock.call_args[0]
    assert call_args[1] is existing
    updates = call_args[2]
    assert updates["slug"] == "site-gen-test"
    assert updates["address"] == "1 Test Road"
    assert updates["color_scheme"] in COLOR_PRESETS


async def test_generate_site_accepts_explicit_color_scheme(service, mock_db):
    existing = _make_institute(owner_id=4)
    update_mock = AsyncMock(return_value=_make_institute(owner_id=4))

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=None)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        await service.generate_site(
            mock_db,
            10,
            slug="color-test",
            address="2 Test Road",
            phone_public="9876543210",
            email_public="hi@example.com",
            description="Bio tuition",
            course_fee_display="Rs 2500/month",
            color_scheme="maroon",
        )

    updates = update_mock.call_args[0][2]
    assert updates["color_scheme"] == "maroon"


async def test_generate_site_rejects_invalid_color_scheme(service, mock_db):
    existing = _make_institute(owner_id=4)
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=None)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        with pytest.raises(ValueError):
            await service.generate_site(
                mock_db,
                10,
                slug="bad-color",
                address="x",
                phone_public="9876543210",
                email_public="hi@example.com",
                description="x",
                course_fee_display="x",
                color_scheme="neon-pink",
            )

    update_mock.assert_not_called()


async def test_generate_site_rejects_unknown_institute_id(service, mock_db):
    with patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="No institute found"):
            await service.generate_site(
                mock_db,
                999999,
                slug="ghost",
                address="x",
                phone_public="9876543210",
                email_public="hi@example.com",
                description="x",
                course_fee_display="x",
            )


async def test_generate_site_rejects_slug_taken_by_different_institute(service, mock_db):
    existing = _make_institute(owner_id=4)
    other_institute = _make_institute(owner_id=7)
    other_institute.id = 99
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=other_institute)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        with pytest.raises(ValueError, match="already in use"):
            await service.generate_site(
                mock_db,
                10,
                slug="taken-slug",
                address="x",
                phone_public="9876543210",
                email_public="hi@example.com",
                description="x",
                course_fee_display="x",
            )

    update_mock.assert_not_called()


async def test_generate_site_allows_resaving_own_existing_slug(service, mock_db):
    existing = _make_institute(owner_id=4)
    existing.slug = "resave-test"
    update_mock = AsyncMock(return_value=existing)

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "get_by_slug", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        await service.generate_site(
            mock_db,
            10,
            slug="resave-test",
            address="new address",
            phone_public="9876543210",
            email_public="hi@example.com",
            description="new",
            course_fee_display="new",
        )

    update_mock.assert_called_once()


async def test_generate_site_rejects_invalid_slug_format(service, mock_db):
    existing = _make_institute(owner_id=4)
    update_mock = AsyncMock()

    with (
        patch.object(service.institute_repo, "get_by_id", new=AsyncMock(return_value=existing)),
        patch.object(service.institute_repo, "update", new=update_mock),
    ):
        with pytest.raises(ValueError):
            await service.generate_site(
                mock_db,
                10,
                slug="Not A Valid Slug!",
                address="x",
                phone_public="9876543210",
                email_public="hi@example.com",
                description="x",
                course_fee_display="x",
            )

    update_mock.assert_not_called()
```

Add `from services.site_color_presets import COLOR_PRESETS` to the top of the file's imports (`import pytest` is already there).

Note: `test_generate_site_rejects_invalid_slug_format` doesn't mock `get_by_slug` — the implementation in Step 4 validates slug format *before* checking uniqueness, so `get_by_slug` is never reached for a malformed slug. If your implementation checks in a different order, add that mock too.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_institute_service.py -v -k "public_by_slug or generate_site"`
Expected: FAIL with `AttributeError: 'InstituteService' object has no attribute 'get_public_by_slug'` (and similarly for `generate_site`).

- [ ] **Step 4: Implement both methods**

In `services/institute_service.py`, add the import at the top:

```python
import re

from services.site_color_presets import resolve_color_scheme
```

Add after `test_razorpay_connection` (before `def get_institute_service():`):

```python
    async def get_public_by_slug(self, db: AsyncSession, slug: str) -> InstituteSchema | None:
        if not slug:
            return None
        return await self.institute_repo.get_by_slug(db, slug)

    async def generate_site(
        self,
        db: AsyncSession,
        institute_id: int,
        *,
        slug: str,
        address: str,
        phone_public: str,
        email_public: str,
        description: str,
        course_fee_display: str,
        color_scheme: str | None = None,
    ) -> InstituteSchema:
        """Persist Tier 2 site-generator content for an institute (Task F.8).

        Raises:
            ValueError: If `institute_id` doesn't exist, `slug` isn't URL-safe,
                `slug` is already taken by a *different* institute, or
                `color_scheme` isn't one of the fixed presets.
        """
        institute = await self.institute_repo.get_by_id(db, institute_id)
        if not institute:
            raise ValueError(f"No institute found with id {institute_id}")

        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
            raise ValueError(
                "slug must be lowercase alphanumeric with hyphens only, e.g. 'bedants-tuition'"
            )

        existing = await self.institute_repo.get_by_slug(db, slug)
        if existing is not None and existing.id != institute_id:
            raise ValueError(f"slug '{slug}' is already in use by another institute")

        resolved_color_scheme = resolve_color_scheme(slug, color_scheme)

        updates = {
            "slug": slug,
            "address": address,
            "phone_public": phone_public,
            "email_public": email_public,
            "description": description,
            "course_fee_display": course_fee_display,
            "color_scheme": resolved_color_scheme,
        }
        return await self.institute_repo.update(db, institute, updates)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_institute_service.py -v`
Expected: PASS — all institute service tests.

- [ ] **Step 6: Run gitnexus_detect_changes and full suite**

Run: `gitnexus_detect_changes()` — confirm only `InstituteService` (new methods) and the test file are affected, nothing in unrelated flows.
Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add services/institute_service.py tests/test_institute_service.py
git commit -m "feat: add InstituteService.get_public_by_slug and generate_site (Task F.8 Tier 2)"
```

---

### Task 5: Public read endpoint

**Files:**
- Create: `routes/responses/public_institute_response.py`
- Create: `routes/public_route.py`
- Modify: `app.py`
- Create: `tests/test_public_routes.py`

**Interfaces:**
- Consumes: `InstituteService.get_public_by_slug` (Task 4), `get_institute_service` (existing factory), `get_db` (existing, from `db.session`).
- Produces: `GET /public/institute/{slug}` — 200 with `PublicInstituteResponse` body, 404 if not found. No later task in this plan depends on this route directly (the generator app calls it over HTTP, not as a Python import).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_public_routes.py`:

```python
"""
Tests for routes/public_route.py — the unauthenticated public institute endpoint
used by the Tier 2 site generator (Task F.8).
"""

from unittest.mock import AsyncMock, MagicMock

from models.institute_base import InstituteSchema, RazorpayStatus
from services.institute_service import InstituteService, get_institute_service


def _fake_institute(**overrides) -> InstituteSchema:
    defaults = dict(
        id=1,
        owner_id=1,
        name="Test Institute",
        city="Delhi",
        join_code="TEST0001",
        razorpay_key_id="rzp_live_should_not_leak",
        razorpay_status=RazorpayStatus.CONNECTED,
        slug="test-institute",
        address="1 Test Road",
        phone_public="9876543210",
        email_public="hi@example.com",
        description="Maths tuition",
        course_fee_display="Rs 3000/month",
        color_scheme="teal",
    )
    defaults.update(overrides)
    return InstituteSchema(**defaults)


async def test_get_public_institute_returns_200_with_allowed_fields(client):
    from app import app

    svc = MagicMock(spec=InstituteService)
    svc.get_public_by_slug = AsyncMock(return_value=_fake_institute())
    app.dependency_overrides[get_institute_service] = lambda: svc

    try:
        resp = await client.get("/public/institute/test-institute")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Institute"
    assert data["color_scheme"] == "teal"
    assert "owner_id" not in data
    assert "join_code" not in data
    assert "razorpay_key_id" not in data
    assert "razorpay_status" not in data


async def test_get_public_institute_returns_404_for_unknown_slug(client):
    from app import app

    svc = MagicMock(spec=InstituteService)
    svc.get_public_by_slug = AsyncMock(return_value=None)
    app.dependency_overrides[get_institute_service] = lambda: svc

    try:
        resp = await client.get("/public/institute/does-not-exist")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_public_routes.py -v`
Expected: FAIL — 404 (route doesn't exist / `ModuleNotFoundError` for `routes.public_route` if imported elsewhere) since neither the route nor the response schema exist yet.

- [ ] **Step 3: Implement the response schema**

Create `routes/responses/public_institute_response.py`:

```python
from pydantic import BaseModel


class PublicInstituteResponse(BaseModel):
    name: str
    city: str
    address: str | None
    phone_public: str | None
    email_public: str | None
    description: str | None
    course_fee_display: str | None
    color_scheme: str | None

    model_config = {"from_attributes": True}
```

This is an explicit allow-list — it must never gain `owner_id`, `join_code`, or any `razorpay_*` field, even if `InstituteSchema` grows more fields later.

- [ ] **Step 4: Implement the route**

Create `routes/public_route.py`:

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from routes.responses.public_institute_response import PublicInstituteResponse
from services.institute_service import InstituteService, get_institute_service

router = APIRouter(prefix="/public")

InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


@router.get(
    "/institute/{slug}",
    summary="Public institute info for the Tier 2 site generator",
    response_model=PublicInstituteResponse,
)
async def get_public_institute(
    slug: str,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """No auth — called server-to-server by the batchbook-site-generator Vercel
    function, keyed only by slug. Response is an explicit allow-list
    (PublicInstituteResponse), never "institute minus a few fields"."""
    institute = await institute_service.get_public_by_slug(db, slug)
    if not institute:
        raise HTTPException(status_code=404, detail="No public site configured for this slug")
    return institute
```

- [ ] **Step 5: Register the router in `app.py`**

Add the import alongside the other route imports (alphabetical, after `from routes.parent_route import router as parent_router`):

```python
from routes.public_route import router as public_router
```

Add the registration alongside the other `app.include_router` calls:

```python
app.include_router(router=public_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_public_routes.py -v`
Expected: PASS — both tests.

- [ ] **Step 7: Run gitnexus_detect_changes and full suite**

Run: `gitnexus_detect_changes()` — confirm the new route/response symbols and `app.py`'s router registration are the only changes.
Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add routes/responses/public_institute_response.py routes/public_route.py app.py tests/test_public_routes.py
git commit -m "feat: add GET /public/institute/{slug} for the Tier 2 site generator (Task F.8)"
```

---

### Task 6: Admin write endpoint

**Files:**
- Create: `routes/requests/generate_site_request.py`
- Modify: `routes/admin_route.py`
- Modify: `tests/test_admin_routes.py`

**Interfaces:**
- Consumes: `InstituteService.generate_site` (Task 4), `_verify_admin_secret` (existing, in `routes/admin_route.py`), `get_institute_service` (existing).
- Produces: `POST /admin/institute/{institute_id}/generate-site` — 200 with `{"public_url": "https://{slug}.batchbook.in"}`, 400 for `ValueError` from the service (bad slug/color-scheme/taken-slug), 404 for unknown `institute_id`, 401/503 from the existing admin-secret guard.

- [ ] **Step 1: Run impact analysis on `routes/admin_route.py`'s router before editing**

Run: `gitnexus_impact({target: "admin_route", direction: "upstream"})` (or the equivalent target name GitNexus resolves for this file/router). Report blast radius — this file is only mounted once in `app.py`, so risk should be low. Confirm no HIGH/CRITICAL before proceeding.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_admin_routes.py`:

```python
from services.institute_service import InstituteService, get_institute_service
from models.institute_base import InstituteSchema


async def test_generate_site_requires_admin_secret_header(client):
    with patch("routes.admin_route.get_settings") as mock_settings:
        mock_settings.return_value.admin_backfill_secret = "s3cr3t"

        resp = await client.post(
            "/admin/institute/1/generate-site",
            json={
                "slug": "test-slug",
                "address": "x",
                "phone_public": "9876543210",
                "email_public": "hi@example.com",
                "description": "x",
                "course_fee_display": "x",
            },
        )

    assert resp.status_code == 401


async def test_generate_site_succeeds_with_correct_secret(client):
    from app import app

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.generate_site = AsyncMock(
        return_value=InstituteSchema(
            id=1, owner_id=1, name="Test", city="Delhi", join_code="TEST0001",
            slug="test-slug", color_scheme="teal",
        )
    )
    app.dependency_overrides[get_institute_service] = lambda: institute_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/institute/1/generate-site",
                json={
                    "slug": "test-slug",
                    "address": "1 Test Road",
                    "phone_public": "9876543210",
                    "email_public": "hi@example.com",
                    "description": "Maths tuition",
                    "course_fee_display": "Rs 3000/month",
                },
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["public_url"] == "https://test-slug.batchbook.in"


async def test_generate_site_returns_400_on_value_error(client):
    from app import app

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.generate_site = AsyncMock(side_effect=ValueError("slug already taken"))
    app.dependency_overrides[get_institute_service] = lambda: institute_svc

    try:
        with patch("routes.admin_route.get_settings") as mock_settings:
            mock_settings.return_value.admin_backfill_secret = "s3cr3t"

            resp = await client.post(
                "/admin/institute/1/generate-site",
                json={
                    "slug": "taken",
                    "address": "x",
                    "phone_public": "9876543210",
                    "email_public": "hi@example.com",
                    "description": "x",
                    "course_fee_display": "x",
                },
                headers={"X-Admin-Secret": "s3cr3t"},
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_admin_routes.py -v -k generate_site`
Expected: FAIL — 404 Not Found (route doesn't exist yet).

- [ ] **Step 4: Implement the request schema**

Create `routes/requests/generate_site_request.py`:

```python
from pydantic import BaseModel


class GenerateSiteRequest(BaseModel):
    slug: str
    address: str
    phone_public: str
    email_public: str
    description: str
    course_fee_display: str
    color_scheme: str | None = None
```

- [ ] **Step 5: Implement the route**

In `routes/admin_route.py`, add imports:

```python
from routes.requests.generate_site_request import GenerateSiteRequest
from services.institute_service import InstituteService, get_institute_service
```

Add the dependency alias near `FeeServiceDep`:

```python
InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]
```

Add the new route at the end of the file:

```python
@router.post(
    "/institute/{institute_id}/generate-site",
    summary="Generate/update a Tier 2 site-generator page for an institute",
    dependencies=[Depends(_verify_admin_secret)],
)
async def generate_site(
    institute_id: int,
    request: GenerateSiteRequest,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """Admin-only (X-Admin-Secret) — same pattern as backfill-payment-links.
    BatchBook ops calls this after collecting an owner's site content over
    WhatsApp/call, for owners who won't self-serve a Tier 1 site themselves."""
    try:
        institute = await institute_service.generate_site(
            db,
            institute_id,
            slug=request.slug,
            address=request.address,
            phone_public=request.phone_public,
            email_public=request.email_public,
            description=request.description,
            course_fee_display=request.course_fee_display,
            color_scheme=request.color_scheme,
        )
    except ValueError as e:
        message = str(e)
        status_code = 404 if message.startswith("No institute found") else 400
        raise HTTPException(status_code=status_code, detail=message) from e
    return {"public_url": f"https://{institute.slug}.batchbook.in"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_admin_routes.py -v`
Expected: PASS — all admin route tests, including the 3 new ones.

- [ ] **Step 7: Run gitnexus_detect_changes and full suite**

Run: `gitnexus_detect_changes()` — confirm `routes/admin_route.py`'s new endpoint and the new request schema are the only changes.
Run: `uv run pytest -v`
Expected: all tests pass (should be 335+ now, up from the 349 baseline noted in PhaseF.md plus everything added in this plan).

- [ ] **Step 8: Commit**

```bash
git add routes/requests/generate_site_request.py routes/admin_route.py tests/test_admin_routes.py
git commit -m "feat: add POST /admin/institute/{id}/generate-site (Task F.8 Tier 2)"
```

---

### Task 7: `batchbook-site-generator` — new repo scaffold + render function

**Files (new repo, sibling to `BatchBook/` — i.e. `../batchbook-site-generator` relative to this repo root):**
- Create: `package.json`
- Create: `vercel.json`
- Create: `api/colorPresets.js`
- Create: `api/render.js`
- Create: `api/[[...slug]].js`
- Create: `.env.example`
- Create: `README.md`
- Create: `test/render.test.js`

**Interfaces:**
- Consumes (over HTTP, not import): `GET /public/institute/{slug}` from Task 5, response shape matching `PublicInstituteResponse`.
- Produces: nothing consumed by later tasks in this plan (Task 8 only edits docs).

- [ ] **Step 1: Create the sibling repo directory and initialize git**

Run:
```bash
mkdir -p ../batchbook-site-generator/api ../batchbook-site-generator/test
cd ../batchbook-site-generator
git init
```

- [ ] **Step 2: Create `package.json`**

```json
{
  "name": "batchbook-site-generator",
  "version": "1.0.0",
  "private": true,
  "description": "Tier 2 wildcard-subdomain site generator for BatchBook institutes without their own website (Task F.8).",
  "type": "commonjs",
  "scripts": {
    "test": "node --test test/"
  }
}
```

- [ ] **Step 3: Create `vercel.json`**

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/api/[[...slug]]" }
  ]
}
```

- [ ] **Step 4: Create `.env.example`**

```
BATCHBOOK_API_BASE_URL=https://api.batchbook.in
```

- [ ] **Step 5: Write the failing render test**

Create `test/render.test.js`:

```js
const test = require("node:test");
const assert = require("node:assert");
const { renderInstitutePage, renderNotFoundPage } = require("../api/render.js");

test("renderInstitutePage includes name, address, and description", () => {
  const html = renderInstitutePage({
    name: "Bedant Classes",
    city: "Gurugram",
    address: "123 MG Road, Gurugram",
    phone_public: "9999999999",
    email_public: "hi@example.com",
    description: "Chemistry tuition for Class 11-12",
    course_fee_display: "Rs 3000/month",
    color_scheme: "teal",
  });

  assert.ok(html.includes("Bedant Classes"));
  assert.ok(html.includes("123 MG Road, Gurugram"));
  assert.ok(html.includes("Chemistry tuition for Class 11-12"));
  assert.ok(html.includes("Rs 3000/month"));
});

test("renderInstitutePage inlines the resolved color preset's hex values", () => {
  const html = renderInstitutePage({
    name: "Test",
    city: "Delhi",
    address: "x",
    phone_public: "x",
    email_public: "x",
    description: "x",
    course_fee_display: "x",
    color_scheme: "maroon",
  });

  assert.ok(html.includes("#9F1239"));
});

test("renderInstitutePage includes required policy sections", () => {
  const html = renderInstitutePage({
    name: "Test",
    city: "Delhi",
    address: "x",
    phone_public: "x",
    email_public: "x",
    description: "x",
    course_fee_display: "x",
    color_scheme: "indigo",
  });

  assert.ok(html.includes("Refund"));
  assert.ok(html.includes("Terms"));
  assert.ok(html.includes("Privacy Policy"));
  assert.ok(html.includes("Grievance"));
});

test("renderNotFoundPage returns a plain not-set-up page", () => {
  const html = renderNotFoundPage();
  assert.ok(html.toLowerCase().includes("not"));
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `node --test test/`
Expected: FAIL — `Error: Cannot find module '../api/render.js'`

- [ ] **Step 7: Implement `api/colorPresets.js`**

This must stay byte-identical (same names, same hex values) to `services/site_color_presets.py`'s `COLOR_PRESETS` in the BatchBook backend — see Global Constraints.

```js
const COLOR_PRESETS = {
  indigo: { primary: "#3730A3", accent: "#6366F1", background: "#F5F5FF" },
  teal: { primary: "#0F766E", accent: "#14B8A6", background: "#F0FDFA" },
  maroon: { primary: "#9F1239", accent: "#E11D48", background: "#FFF1F2" },
  forest: { primary: "#166534", accent: "#22C55E", background: "#F0FDF4" },
  slate: { primary: "#1E293B", accent: "#475569", background: "#F8FAFC" },
  amber: { primary: "#92400E", accent: "#F59E0B", background: "#FFFBEB" },
  plum: { primary: "#6B21A8", accent: "#A855F7", background: "#FAF5FF" },
  ocean: { primary: "#075985", accent: "#0EA5E9", background: "#F0F9FF" },
  terracotta: { primary: "#9A3412", accent: "#EA580C", background: "#FFF7ED" },
  "charcoal-gold": { primary: "#292524", accent: "#CA8A04", background: "#FAFAF9" },
};

const DEFAULT_PRESET = COLOR_PRESETS.indigo;

module.exports = { COLOR_PRESETS, DEFAULT_PRESET };
```

- [ ] **Step 8: Implement `api/render.js`**

```js
const { COLOR_PRESETS, DEFAULT_PRESET } = require("./colorPresets.js");

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderInstitutePage(institute) {
  const colors = COLOR_PRESETS[institute.color_scheme] || DEFAULT_PRESET;
  const name = escapeHtml(institute.name);

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>${name}</title>
<style>
  :root {
    --primary: ${colors.primary};
    --accent: ${colors.accent};
    --background: ${colors.background};
  }
  body { font-family: system-ui, sans-serif; background: var(--background); color: #1a1a1a; margin: 0; padding: 0; }
  header { background: var(--primary); color: white; padding: 2rem 1.5rem; }
  main { max-width: 720px; margin: 0 auto; padding: 1.5rem; }
  h1 { margin: 0; }
  section { margin-bottom: 2rem; }
  h2 { color: var(--primary); border-bottom: 2px solid var(--accent); padding-bottom: 0.25rem; }
  .fee { font-weight: bold; color: var(--accent); }
</style>
</head>
<body>
<header><h1>${name}</h1><p>${escapeHtml(institute.city)}</p></header>
<main>
  <section>
    <h2>About</h2>
    <p>${escapeHtml(institute.description)}</p>
    <p class="fee">Fee: ${escapeHtml(institute.course_fee_display)}</p>
  </section>
  <section>
    <h2>Contact</h2>
    <p>Address: ${escapeHtml(institute.address)}</p>
    <p>Phone: ${escapeHtml(institute.phone_public)}</p>
    <p>Email: ${escapeHtml(institute.email_public)}</p>
  </section>
  <section>
    <h2>Refund &amp; Cancellation Policy</h2>
    <p>Fees paid for a given month are non-refundable once classes for that month have begun. Refund requests made before the first class of a month will be processed within 7 business days.</p>
  </section>
  <section>
    <h2>Terms &amp; Conditions</h2>
    <p>Enrollment is confirmed on receipt of payment. Course schedules may be adjusted with prior notice to enrolled students.</p>
  </section>
  <section>
    <h2>Privacy Policy</h2>
    <p>Student and parent contact information is used solely for enrollment, attendance, and fee communication, and is never sold or shared with third parties.</p>
  </section>
  <section>
    <h2>Grievance Redressal</h2>
    <p>For any complaint or concern, contact us directly at the phone number or email above. We aim to respond within 2 business days.</p>
  </section>
</main>
</body>
</html>`;
}

function renderNotFoundPage() {
  return `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Site not found</title></head>
<body>
<h1>This site is not set up yet.</h1>
<p>If you're the institute owner, contact BatchBook support.</p>
</body>
</html>`;
}

module.exports = { renderInstitutePage, renderNotFoundPage };
```

- [ ] **Step 9: Run test to verify it passes**

Run: `node --test test/`
Expected: PASS — all 4 tests.

- [ ] **Step 10: Implement the catch-all handler `api/[[...slug]].js`**

```js
const { renderInstitutePage, renderNotFoundPage } = require("./render.js");

function extractSlug(host) {
  if (!host) return null;
  const hostname = host.split(":")[0];
  const parts = hostname.split(".");
  // e.g. "bedants-tuition.batchbook.in" -> "bedants-tuition"
  // Anything not matching the 3-label *.batchbook.in shape (e.g. bare
  // "batchbook.in", "localhost", or a Vercel preview URL) has no valid slug.
  if (parts.length !== 3) return null;
  return parts[0];
}

module.exports = async function handler(req, res) {
  const slug = extractSlug(req.headers.host);
  const apiBase = process.env.BATCHBOOK_API_BASE_URL;

  if (!slug || !apiBase) {
    res.statusCode = 404;
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.end(renderNotFoundPage());
    return;
  }

  let apiResponse;
  try {
    apiResponse = await fetch(`${apiBase}/public/institute/${encodeURIComponent(slug)}`);
  } catch (err) {
    res.statusCode = 502;
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.end(renderNotFoundPage());
    return;
  }

  if (!apiResponse.ok) {
    res.statusCode = 404;
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.end(renderNotFoundPage());
    return;
  }

  const institute = await apiResponse.json();
  res.statusCode = 200;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.end(renderInstitutePage(institute));
};
```

- [ ] **Step 11: Write `README.md`**

```markdown
# batchbook-site-generator

Tier 2 fallback for Task F.8: generates a real, crawler-visible business page
for BatchBook owners on a wildcard subdomain (`{slug}.batchbook.in`), for
owners who won't self-serve a Tier 1 site (Google Sites/Carrd) themselves.

One Vercel serverless function (`api/[[...slug]].js`) reads the `Host`
header, fetches `GET {BATCHBOOK_API_BASE_URL}/public/institute/{slug}` from
the BatchBook backend, and renders server-side HTML — no client-side JS
needed for content, since Razorpay's site-approval crawler must see real
rendered content.

## Local development

```bash
npm install -g vercel   # if not already installed
cp .env.example .env
# edit .env: point BATCHBOOK_API_BASE_URL at your local `uvicorn` (e.g. http://localhost:8000)
vercel dev
```

Then in another terminal, simulate a subdomain request:

```bash
curl -H "Host: some-test-slug.batchbook.in" http://localhost:3000/
```

## Tests

```bash
npm test
```

## Deploying (manual steps — not automated)

1. Push this repo to GitHub (`github.com/bedantsharma/batchbook-site-generator`).
2. Import it as a new Vercel project.
3. Set `BATCHBOOK_API_BASE_URL=https://api.batchbook.in` in the Vercel project's
   environment variables.
4. In Namecheap (Advanced DNS for `batchbook.in`), add a `*` CNAME record
   pointing at the target Vercel gives you for this project — same pattern
   used for the `bedant-classes` CNAME, just wildcarded.
5. In Vercel → Project → Settings → Domains, add `*.batchbook.in`.
6. Content for any given institute is entered via BatchBook's
   `POST /admin/institute/{institute_id}/generate-site` endpoint (see
   `PhaseF.md` Task F.8 and `docs/superpowers/specs/2026-07-06-f8-tier2-site-generator-design.md`
   in the main BatchBook repo) — not through this repo.
```

- [ ] **Step 12: Commit**

```bash
git add package.json vercel.json api/ .env.example README.md test/
git commit -m "feat: scaffold batchbook-site-generator (Task F.8 Tier 2)"
```

- [ ] **Step 13: Report the GitHub push step back to the user**

This step needs a GitHub account/token this session may not have — in your task summary, tell the user: "The `batchbook-site-generator` repo is initialized locally at `../batchbook-site-generator` with a passing test suite. Create a GitHub repo (e.g. `github.com/bedantsharma/batchbook-site-generator`) and push it, then follow the README's 'Deploying' steps to connect Vercel and DNS." Do not attempt to create the GitHub repo or push yourself unless the user explicitly asks for that in this session.

---

### Task 8: Docs update + final verification

**Files:**
- Modify: `PhaseF.md`
- Modify: `BATCHBOOK_ROADMAP_V2.md`

**Interfaces:**
- Consumes: nothing code-level — this task only updates checklists to reflect Tasks 1–7.

- [ ] **Step 1: Check off the completed Task F.8 checklist items in `PhaseF.md`**

In the `### Task F.8` section's checklist, mark these as done (change `- [ ]` to `- [x]`), since Tasks 1–7 above implement them:
- `Alembic migration: add slug ... color_scheme ... to Institute`
- `GET /public/institute/{slug}`
- `POST /admin/institute/{institute_id}/generate-site`
- `The generator itself: a single small server-rendered app/function ...`

Leave these unchecked (still genuinely pending — external/manual):
- `Wildcard DNS: *.batchbook.in CNAME in Namecheap → Vercel; ...`
- `app.py CORS: switch from the static allow_origins list to allow_origin_regex ...` — also add a one-line note referencing this plan's decision to skip it (see the design spec's CORS decision) so a future reader doesn't think it was missed by accident.
- `Write the Tier 1 self-serve guide: ...`
- `Leave the existing pilot page at bedant-classes.batchbook.in as-is ...` (this one was never something to "do", just a note — leave as-is)

Update the task's status line (currently `### Task F.8 — ... Website onboarding for every future owner...`) and its `**Verified by:**` line to reflect: code-complete for the engineering pieces (migration, endpoints, generator app), pending the manual DNS/Vercel steps and Tier 1 guide.

- [ ] **Step 2: Update `BATCHBOOK_ROADMAP_V2.md`'s Phase F status line**

In the Roadmap Overview table's Phase F row, update the parenthetical to note F.8's Tier 2 engineering is code-complete (migration + endpoints + generator repo scaffolded), pending DNS/Vercel wiring and the Tier 1 guide.

- [ ] **Step 3: Final full verification**

Run: `uv run pytest -v`
Expected: all tests pass, including everything added across Tasks 1–6.

Run: `gitnexus_detect_changes()` one more time at the end — confirm the cumulative set of affected symbols across this whole plan matches what was intended (InstituteSchema, InstituteRepository, InstituteService, the new public/admin routes) and nothing in an unrelated flow (e.g. student dashboard, attendance) shows up.

- [ ] **Step 4: Commit**

```bash
git add PhaseF.md BATCHBOOK_ROADMAP_V2.md
git commit -m "docs: update PhaseF.md and roadmap for Task F.8 Tier 2 engineering completion"
```

---

## Out of scope (do not implement in this plan)

- Task F.8's Tier 1 self-serve guide (Google Sites/Carrd walkthrough) — separate, non-code deliverable.
- A self-serve Settings-page version for owners to edit their own Tier 2 site content.
- The `app.py` CORS `allow_origin_regex` change — explicitly skipped per the design spec's CORS decision.
- Actually registering DNS records, connecting the Vercel project, or pushing `batchbook-site-generator` to GitHub — these are manual steps for the account owner, called out explicitly in Task 7 Step 13 and Task 8.
