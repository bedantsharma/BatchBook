from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Health check for Render/uptime monitoring")
async def health_check():
    """No auth, no DB/Supabase calls — just confirms the process is up and
    able to serve requests. If the server is down, this route is unreachable
    and the platform's request simply fails/times out."""
    return {"status": "ok"}
