from uuid import UUID

from supabase import AsyncClient


async def get_current_user_id(supabase: AsyncClient, authorization: str) -> UUID:
    token = authorization.removeprefix("Bearer ").strip()
    response = await supabase.auth.get_user(token)
    return UUID(str(response.user.id))
