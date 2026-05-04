from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase._async.client import create_client

from clients import supabase_client
from config import get_settings
from routes.student_route import router as student_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 2. Initialize once on startup
    supabase_client.supabase = await create_client(
        get_settings().supabase_url, get_settings().supabase_key
    )
    yield
    # 3. Cleanup once on shutdown
    await (
        supabase_client.supabase.auth.sign_out()
    )  # Optional, usually not needed for service clients


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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router=student_router)
