from contextlib import asynccontextmanager

from supabase._async.client import create_client
from config import get_settings
from clients import supabase_client
from routes.student_route import router as student_router
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 2. Initialize once on startup
    supabase_client.supabase = await create_client(
        get_settings().supabase_url,
        get_settings().supabase_key
    )
    yield
    # 3. Cleanup once on shutdown
    await supabase_client.supabase.auth.sign_out() # Optional, usually not needed for service clients

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
    lifespan=lifespan
)

app.include_router(router=student_router)