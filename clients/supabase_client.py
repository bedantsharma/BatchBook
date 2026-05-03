from contextlib import asynccontextmanager
from fastapi import FastAPI
from supabase._async.client import AsyncClient, create_client
from config import get_settings

# 1. Define a global client variable
supabase: AsyncClient = None



# 4. Dependency simply returns the existing client
async def get_supabase_client() -> AsyncClient:
    return supabase