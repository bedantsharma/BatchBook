---
name: new-route
description: Scaffold a complete new FastAPI domain for BatchBook. Creates model, repository, service, route, request/response schemas, and registers the router. Usage: /new-route <domain> e.g. /new-route batch
---

# New Route Scaffold

Scaffold all standard layers for a new BatchBook domain. The argument is the domain name in snake_case (e.g. `batch`, `fee_structure`).

## Standard File Set to Create

Given domain `<domain>` (e.g. `batch`):

| File | Purpose |
|------|---------|
| `models/<domain>_base.py` | SQLAlchemy ORM model (table: `"<Domain>"`) |
| `repositories/<domain>_repository.py` | DB query layer — raw SQLAlchemy, no business logic |
| `services/<domain>_service.py` | Business logic layer + `get_<domain>_service()` factory |
| `routes/<domain>_route.py` | FastAPI router with `prefix="/<domain>"` |
| `routes/requests/<action>_<domain>_request.py` | Pydantic request schemas (one per action) |
| `routes/responses/<domain>_response.py` | Pydantic response schema |
| `tests/test_<domain>_routes.py` | Async route tests using `AsyncClient` |
| `tests/test_<domain>_service.py` | Unit tests for service layer |

## Conventions to Follow

### Model (`models/<domain>_base.py`)
- Extend `Base` from `db.base`
- `__tablename__` = title-case domain name (e.g. `"Batch"`)
- Always include `id = Column(Integer, primary_key=True, autoincrement=True)`
- Always include `created_at = Column(DateTime, default=datetime.utcnow)`
- Import all models in `models/__init__.py` (check the file and add the import)

### Repository (`repositories/<domain>_repository.py`)
- Class named `<Domain>Repository`
- Takes `AsyncSession` as parameter on each method (not stored in constructor)
- Returns ORM objects; caller handles serialisation
- Methods are `async def`

### Service (`services/<domain>_service.py`)
- Class named `<Domain>Service`
- Constructor: `self.<domain>_repo = <Domain>Repository()`
- `async def` methods that call the repo and apply business logic
- Factory: `def get_<domain>_service() -> <Domain>Service: return <Domain>Service()`
- Use `get_db` and `get_supabase_client` as FastAPI `Depends`

### Route (`routes/<domain>_route.py`)
- `router = APIRouter(prefix="/<domain>")`
- Auth-protected endpoints use the same `_get_current_*_id` pattern as owner/teacher routes (call `auth_service.get_current_user_id(supabase, authorization)`)
- Use `Annotated[..., Depends(...)]` type aliases at the top

### Request/Response Schemas
- Pydantic `BaseModel` subclasses
- In `routes/requests/` and `routes/responses/`
- Named clearly: `Create<Domain>Request`, `Update<Domain>Request`, `<Domain>Response`

### app.py Registration
- Add import: `from routes.<domain>_route import router as <domain>_router`
- Add: `app.include_router(router=<domain>_router)`

### Tests
- Use fixtures from `tests/conftest.py` (`async_client`, `db_session`)
- Pattern: `async def test_<action>_<domain>(async_client: AsyncClient):`
- Mock Supabase auth with the same pattern used in `test_owner_routes.py`

## Steps to Execute

1. Ask the user: what columns/fields does this domain need? (or infer from context if obvious)
2. Run `gitnexus_impact` on `app.py` before modifying it
3. Create all files in order: model → repository → service → route → requests → responses
4. Update `models/__init__.py` with the new model import
5. Register the router in `app.py`
6. Run `uv run alembic revision --autogenerate -m "add <domain> table"` and report the migration filename
7. Run `uv run pytest -v --tb=short tests/test_<domain>_routes.py` if tests were created
8. Confirm all files created and migration generated

## Example Invocation

`/new-route batch` → creates Batch domain: model with name/start_date/end_date/status/institute_id, full CRUD routes under `/batch`.
