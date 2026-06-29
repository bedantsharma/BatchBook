import json
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException
from jwt.algorithms import ECAlgorithm
from supabase import AsyncClient

from config import get_settings

_public_key_cache: object | None = None


async def _get_public_key(supabase_url: str) -> object:
    """Fetch and cache the EC public key from Supabase's JWKS endpoint.

    Supabase exposes the signing public key at:
        {supabase_url}/auth/v1/.well-known/jwks.json
    The key is cached for the lifetime of the process. A server restart
    picks up a rotated key (rotation requires a manual Supabase dashboard action).
    """
    global _public_key_cache
    if _public_key_cache is not None:
        return _public_key_cache

    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_url, timeout=5.0)
        resp.raise_for_status()
        jwks = resp.json()

    key_data = next((k for k in jwks["keys"] if k.get("kty") == "EC"), None)
    if key_data is None:
        raise RuntimeError("No EC key found in JWKS response from Supabase")

    _public_key_cache = ECAlgorithm.from_jwk(json.dumps(key_data))
    return _public_key_cache


async def get_current_user_id(supabase: AsyncClient, authorization: str) -> UUID:
    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()

    try:
        public_key = await _get_public_key(settings.supabase_url)
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
