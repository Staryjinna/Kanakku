from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import AppSettings, CurrentUser, Db
from app.observability import service

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: CurrentUser, settings: AppSettings) -> dict[str, Any]:
    if user["email"] not in settings.admin_email_set:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


@router.get("/metrics")
async def metrics(
    conn: Db,
    _: Annotated[dict[str, Any], Depends(require_admin)],
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> dict[str, Any]:
    return service.metrics(conn, days)
