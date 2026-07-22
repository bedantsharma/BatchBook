import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.concurrency import iterate_in_threadpool
from supabase._async.client import create_client

from clients import supabase_client
from config import get_settings
from rate_limiter import limiter
from request_logging import MAX_LOGGED_BYTES, capture_and_redact
from routes.admin_route import router as admin_router
from routes.attendance_route import router as attendance_router
from routes.batch_route import router as batch_router
from routes.enrollment_route import router as enrollment_router
from routes.fee_route import router as fee_router
from routes.owner_route import router as owner_router
from routes.parent_route import router as parent_router
from routes.public_route import router as public_router
from routes.student_dashboard_route import router as student_dashboard_router
from routes.student_route import router as student_router
from routes.teacher_route import router as teacher_router
from routes.test_score_route import router as test_score_router
from routes.webhook_route import router as webhook_router
from scheduler import shutdown_scheduler, start_scheduler
from telemetry import setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    supabase_client.supabase = await create_client(
        get_settings().supabase_url, get_settings().supabase_key
    )
    if get_settings().enable_scheduler:
        start_scheduler()
    yield
    if get_settings().enable_scheduler:
        shutdown_scheduler()


app = FastAPI(
    title="Batch Book",
    description="Clean, well-documented API for batch book application 🚀",
    version="1.0.0",
    contact={
        "name": "Bedant Sharma",
        "email": "bedant.sharma.dev@gmail.com",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_telemetry(app)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def log_and_handle_exceptions(request: Request, call_next):
    """Log every request with method, url, status, and elapsed time,
    including redacted request/response bodies and query/path params as
    structured fields. Also catches any unhandled exception that escapes a
    route handler so the client always receives a well-formed 500 JSON body
    instead of a raw traceback or an empty response.
    """
    start = time.perf_counter()

    request_body_log = None
    request_content_length = request.headers.get("content-length")
    if request_content_length and int(request_content_length) > MAX_LOGGED_BYTES:
        request_body_log = json.dumps(
            f"[request body too large to capture: {request_content_length} bytes]"
        )
    else:
        raw_body = await request.body()
        if raw_body and "application/json" in request.headers.get("content-type", ""):
            try:
                request_body_log = capture_and_redact(json.loads(raw_body))
            except (json.JSONDecodeError, UnicodeDecodeError):
                request_body_log = None

    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        response_body_log = None
        if "application/json" in response.headers.get("content-type", ""):
            response_content_length = response.headers.get("content-length")
            if response_content_length and int(response_content_length) > MAX_LOGGED_BYTES:
                response_body_log = json.dumps(
                    f"[response body too large to capture: {response_content_length} bytes]"
                )
            else:
                chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(chunks))
                raw_response = b"".join(chunks)
                try:
                    response_body_log = capture_and_redact(json.loads(raw_response))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_body_log = None

        logger.bind(
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
            query_params=capture_and_redact(dict(request.query_params)),
            path_params=capture_and_redact(dict(request.path_params)),
            request_body=request_body_log,
            response_body=response_body_log,
        ).info("request completed")
        return response
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.bind(
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            status_code=500,
            duration_ms=round(elapsed * 1000, 2),
            query_params=capture_and_redact(dict(request.query_params)),
            path_params=capture_and_redact(dict(request.path_params)),
            request_body=request_body_log,
            exception=repr(exc),
        ).error("request failed")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# CORSMiddleware must be added last so it becomes the outermost layer.
# If it were inner (e.g. under log_and_handle_exceptions), any bare JSONResponse
# returned by that handler on exception would skip CORS headers entirely and the
# browser would report a spurious "CORS error" instead of the real 500.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "https://batchbookui.vercel.app",
        "https://batchbook.in",
        "https://www.batchbook.in",
        "http://localhost:8081"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router=student_router)
app.include_router(router=student_dashboard_router)
app.include_router(router=owner_router)
app.include_router(router=teacher_router)
app.include_router(router=parent_router)
app.include_router(router=batch_router)
app.include_router(router=enrollment_router)
app.include_router(router=fee_router)
app.include_router(router=attendance_router)
app.include_router(router=admin_router)
app.include_router(router=test_score_router)
app.include_router(router=webhook_router)
app.include_router(router=public_router)
