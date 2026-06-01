import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from supabase._async.client import create_client

from clients import supabase_client
from config import get_settings
from routes.attendance_route import router as attendance_router
from routes.batch_route import router as batch_router
from routes.enrollment_route import router as enrollment_router
from routes.fee_route import router as fee_router
from routes.owner_route import router as owner_router
from routes.parent_route import router as parent_router
from routes.student_route import router as student_router
from routes.teacher_route import router as teacher_router
from routes.test_score_route import router as test_score_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    supabase_client.supabase = await create_client(
        get_settings().supabase_url, get_settings().supabase_key
    )
    yield


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "https://68cd-2409-40d0-14e9-3bec-b1-11ec-46fe-8ef7.ngrok-free.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_and_handle_exceptions(request: Request, call_next):
    """Log every request with method, path, status, and elapsed time.

    Also catches any unhandled exception that escapes a route handler so the
    client always receives a well-formed 500 JSON body instead of a raw
    traceback or an empty response.
    """
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.3f}s)"
        )
        return response
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc!r}"
        )
        logger.info(f"{request.method} {request.url.path} → 500 ({elapsed:.3f}s)")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(router=student_router)
app.include_router(router=owner_router)
app.include_router(router=teacher_router)
app.include_router(router=parent_router)
app.include_router(router=batch_router)
app.include_router(router=enrollment_router)
app.include_router(router=fee_router)
app.include_router(router=attendance_router)
app.include_router(router=test_score_router)
