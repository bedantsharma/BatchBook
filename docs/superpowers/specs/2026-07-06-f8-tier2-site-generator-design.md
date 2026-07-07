# Task F.8 Tier 2 — BatchBook-Generated Website Fallback

Date: 2026-07-06

## Problem

Task F.2b discovered that Razorpay requires an approved, Education-category business
website before it issues live API keys — not just completed KYC. This blocks every
future owner going through Task F.7's real-onboarding step, not just the pilot
institute (Bedant Classes), which was unblocked by hand-building a one-off static page
at `bedant-classes.batchbook.in`.

PhaseF.md's Task F.8 already decided the shape of the fix: most owners should self-serve
a site via Google Sites/Carrd (Tier 1 — a documentation deliverable, out of scope here).
For owners who won't spend any time/money on that, BatchBook needs to generate a
minimal, real, crawler-visible business page for them on a wildcard subdomain
(`{slug}.batchbook.in`) — this is Tier 2, and is what this spec covers.

## Decisions

- **Scope for this pass:** DB migration + public read endpoint + admin write endpoint
  (all in the existing `BatchBook` backend) + a new standalone generator app + the
  manual external DNS/Vercel steps needed to wire it up. The Tier 1 guide and a
  self-serve owner-facing Settings page for editing Tier 2 content are both explicitly
  deferred (per PhaseF.md, the self-serve version is "not needed at current scale").
- **Generator tech:** a single Vercel serverless function (Node.js), not a framework.
  It reads the `Host` header, extracts the slug, calls BatchBook's public API
  server-side, and returns hand-rendered HTML. No client-side JS is needed for content
  — matters because Razorpay's approval crawler must see real server-rendered content,
  the same reason the pilot page couldn't be a route inside the `batchbookui` SPA.
- **Repo:** new sibling repo `batchbook-site-generator` (its own GitHub repo + Vercel
  project), following the same independence pattern as `batchbookui`, rather than
  folding into an existing repo. Unlike the throwaway pilot page (no git at all), this
  serves every future owner and is worth tracking properly.
- **Content authorship for Tier 2 sites:** since a Tier-2 owner by definition won't fill
  in a form themselves, BatchBook ops collects the content via a real conversation
  (WhatsApp/call) and enters it through the admin endpoint — mirroring the existing
  `POST /admin/backfill-payment-links` pattern (`X-Admin-Secret` header, not a public
  form).
- **CORS:** PhaseF.md's original checklist called for switching `app.py`'s
  `allow_origins` to an `allow_origin_regex` matching `https://.*\.batchbook\.in`. This
  spec skips that: the generator function fetches BatchBook's API server-side
  (Vercel → Render), so no browser ever calls `api.batchbook.in` cross-origin from a
  generated page. Revisit only if a later feature adds client-side JS on these pages
  that calls the API directly from the browser.
- **Color variation:** a fixed list of 10 presets (primary/accent/background triples),
  picked deterministically via `hash(slug) % 10` when not explicitly specified. Per
  PhaseF.md's research, no confirmed Razorpay account freeze has ever been tied to
  templated/visually-similar merchant sites — only behavioral causes (KYC mismatches,
  fraud, volume spikes) — so structural/procedural variation between generated sites is
  unnecessary; color-only variation is enough.

## Section 1 — Data model

New nullable columns on `InstituteSchema` (`models/institute_base.py`), migrated with
Alembic:

```python
slug = Column(String, nullable=True, unique=True, index=True)
address = Column(String, nullable=True)
phone_public = Column(String, nullable=True)
email_public = Column(String, nullable=True)
description = Column(String, nullable=True)
course_fee_display = Column(String, nullable=True)
color_scheme = Column(String, nullable=True)
```

All nullable — existing institutes, and any owner who never needs a Tier 2 site, never
set these. `slug` is unique so two institutes can never collide on a subdomain.

**Fixed color-scheme presets** (name → primary/accent/background hex), validated
against this list wherever `color_scheme` is written:

| Name | Primary | Accent | Background |
|---|---|---|---|
| indigo | `#3730A3` | `#6366F1` | `#F5F5FF` |
| teal | `#0F766E` | `#14B8A6` | `#F0FDFA` |
| maroon | `#9F1239` | `#E11D48` | `#FFF1F2` |
| forest | `#166534` | `#22C55E` | `#F0FDF4` |
| slate | `#1E293B` | `#475569` | `#F8FAFC` |
| amber | `#92400E` | `#F59E0B` | `#FFFBEB` |
| plum | `#6B21A8` | `#A855F7` | `#FAF5FF` |
| ocean | `#075985` | `#0EA5E9` | `#F0F9FF` |
| terracotta | `#9A3412` | `#EA580C` | `#FFF7ED` |
| charcoal-gold | `#292524` | `#CA8A04` | `#FAFAF9` |

This preset table needs to exist in two places that must stay in sync: the Python
backend (for validating `color_scheme` on write) and the Node generator (for mapping a
stored `color_scheme` name to actual CSS variables at render time). Duplicated as plain
data in each codebase — no shared package, since these are two independent repos and
the table is small/static.

## Section 2 — Public read endpoint

New `routes/public_route.py`, registered in `app.py` alongside the other routers:

```
GET /public/institute/{slug}
```

- No auth dependency — this is the one endpoint with zero auth, since the generator
  function calls it unauthenticated from outside BatchBook's own frontend.
- 404 if no institute has that slug (covers both "no such slug" and "slug is null").
- Response schema is an explicit allow-list (new `routes/responses/public_institute_response.py`):
  `name, city, address, phone_public, email_public, description, course_fee_display,
  color_scheme`. Deliberately excludes `owner_id`, `join_code`, and every Razorpay
  field — never "institute minus a few fields", so a future column addition to
  `InstituteSchema` can't accidentally leak through this endpoint.
- New `InstituteRepository.get_by_slug(db, slug)` and
  `InstituteService.get_public_by_slug(db, slug)` following the existing
  `get_by_join_code` pattern in `institute_repository.py`/`institute_service.py`.

## Section 3 — Admin write endpoint

Added to the existing `routes/admin_route.py`, reusing `_verify_admin_secret`:

```
POST /admin/institute/{institute_id}/generate-site
```

- Body (new `routes/requests/generate_site_request.py`): `slug, address, phone_public,
  email_public, description, course_fee_display`, `color_scheme` optional.
- New `InstituteService.generate_site(db, institute_id, ...)`:
  - 404 (raised as `ValueError`, mapped to HTTP 404 in the route) if `institute_id`
    doesn't exist.
  - Validates `slug` is URL-safe (lowercase alphanumeric + hyphens) and not already
    taken by a *different* institute (`ValueError` → `400` if taken).
  - If `color_scheme` given, validates it's one of the 10 preset names (`ValueError` →
    `400` if not); if omitted, computes `PRESET_NAMES[hash(slug) % 10]`.
  - Persists all fields via the existing `institute_repo.update()`.
- Returns the resulting public URL: `https://{slug}.batchbook.in`.

## Section 4 — Generator app (`batchbook-site-generator`, new repo)

```
batchbook-site-generator/
  api/
    [[...slug]].js       # Vercel catch-all — the only route; path is irrelevant,
                         # only the Host header matters
  package.json           # no framework dependency
  vercel.json            # routes every path to the catch-all function
  .env.example           # BATCHBOOK_API_BASE_URL
  README.md              # deploy + DNS steps
```

**Request flow in `[[...slug]].js`:**
1. Read `req.headers.host` (e.g. `bedants-tuition.batchbook.in`), extract the leftmost
   label as the slug.
2. `fetch(`${BATCHBOOK_API_BASE_URL}/public/institute/${slug}`)`.
3. Non-200 (404, or fetch failure) → render a plain "this site isn't set up yet" HTML
   page, itself returned with a 404 status.
4. 200 → render a full HTML page: business name, address, phone, email, course
   description, fee, plus static **Refund & Cancellation Policy / Terms & Conditions /
   Privacy Policy / Grievance Redressal** sections (boilerplate text mirroring the
   structure Razorpay already approved on the pilot page), with the resolved
   `color_scheme` mapped to CSS custom properties inlined in a `<style>` block.
- Single function, single template — every institute's page has the same shape, only
  the injected data and CSS variables vary. Nothing to route on by path since `Host` is
  the only per-institute signal.

## Section 5 — External / manual steps (not automated)

Documented in the new repo's `README.md`, executed by the account owner (dashboard
access this session doesn't have):

1. Namecheap: add a `*` CNAME record for `batchbook.in` → Vercel's target (same pattern
   as the existing `bedant-classes` CNAME, wildcarded).
2. Vercel: add `*.batchbook.in` as a domain on the `batchbook-site-generator` project.
3. Set `BATCHBOOK_API_BASE_URL=https://api.batchbook.in` as an env var on that Vercel
   project.
4. Create the GitHub repo and connect it to a new Vercel project for first deploy.

## Testing plan

- `tests/test_institute_service.py`: `generate_site` — slug uniqueness rejection
  (`ValueError`/400 when taken by a different institute, allowed when re-saving the
  same institute's own existing slug), invalid `color_scheme` rejection, default
  color-scheme hashing is deterministic for a given slug, 404 path for a nonexistent
  `institute_id`.
- `tests/test_institute_repository.py`: `get_by_slug` returns the matching row or
  `None`.
- `tests/test_public_routes.py` (new): `GET /public/institute/{slug}` — 200 with the
  allow-listed fields only (asserts `owner_id`/`join_code`/Razorpay fields are absent
  from the response body), 404 for unknown slug, 404 for an institute with no slug set.
- `tests/test_admin_routes.py`: extend with `generate-site` — missing/wrong
  `X-Admin-Secret` → 401 (already-covered pattern), valid request → 200 with the
  expected public URL, duplicate-slug → 400, unknown `institute_id` → 404.
- Generator app: no live DNS/Vercel dependency needed to test locally — run `vercel dev`
  locally with `BATCHBOOK_API_BASE_URL` pointed at local `uvicorn`, hit it with `curl -H
  "Host: <slug>.batchbook.in"` to confirm both the render and 404 paths before deploying.

## Out of scope

- Task F.8's Tier 1 self-serve guide (Google Sites/Carrd walkthrough) — separate,
  non-code deliverable.
- A self-serve Settings-page version for owners to edit their own Tier 2 site content.
- The `app.py` CORS `allow_origin_regex` change from PhaseF.md's original checklist —
  unused by this design's server-to-server fetch flow; revisit only if a future feature
  needs browser-side calls to the API from a generated page.
- Actually registering DNS records or connecting the Vercel project — documented as
  manual steps for the account owner, not executed in this pass.
