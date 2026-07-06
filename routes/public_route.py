from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from routes.responses.public_institute_response import PublicInstituteResponse
from services.institute_service import InstituteService, get_institute_service

router = APIRouter(prefix="/public")

InstituteServiceDep = Annotated[InstituteService, Depends(get_institute_service)]


@router.get(
    "/institute/{slug}",
    summary="Public institute info for the Tier 2 site generator",
    response_model=PublicInstituteResponse,
)
async def get_public_institute(
    slug: str,
    institute_service: InstituteServiceDep,
    db: AsyncSession = Depends(get_db),
):
    """No auth — called server-to-server by the batchbook-site-generator Vercel
    function, keyed only by slug. Response is an explicit allow-list
    (PublicInstituteResponse), never "institute minus a few fields"."""
    institute = await institute_service.get_public_by_slug(db, slug)
    if not institute:
        raise HTTPException(status_code=404, detail="No public site configured for this slug")
    return institute
