from supabase._async.client import AsyncClient

# 1. Define a global client variable
supabase: AsyncClient = None


# 4. Dependency simply returns the existing client
async def get_supabase_client() -> AsyncClient:
    return supabase
