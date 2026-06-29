from uuid import UUID

import jwt
from fastapi import HTTPException
from supabase import AsyncClient

from config import get_settings


async def get_current_user_id(supabase: AsyncClient, authorization: str) -> UUID:
    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
