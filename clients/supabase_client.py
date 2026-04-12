from typing import AsyncGenerator

from supabase._async.client import AsyncClient, create_client
from core.config import get_settings

async def get_supabase_client() -> AsyncGenerator[AsyncClient, None]:
    client: AsyncClient = await create_client(
        get_settings().supabase_url,
        get_settings().supabase_key
    )
    try:
        yield client
    finally:
        await client.auth.sign_out()  # cleanup