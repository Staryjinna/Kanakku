from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.account import service
from app.auth.deps import COOKIE_NAME, AppSettings, CurrentUser, Db
from app.auth.router import MeResponse, to_me
from app.auth.service import get_user
from app.security import CSRF_COOKIE

router = APIRouter(prefix="/api/account", tags=["account"])


class BusinessUpdate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=150)]
    gstin: Annotated[str | None, Field(max_length=20)] = None
    state_code: str
    language: str = "en"
    onboarding_done: bool | None = None


class DeleteRequest(BaseModel):
    confirm_email: str


@router.patch("/business", response_model=MeResponse)
async def update_business(body: BusinessUpdate, conn: Db, user: CurrentUser, settings: AppSettings):  # type: ignore[no-untyped-def]
    try:
        service.update_business(
            conn,
            user["business_id"],
            name=body.name,
            gstin=body.gstin,
            state_code=body.state_code,
            language=body.language,
            onboarding_done=body.onboarding_done,
        )
    except service.InvalidBusiness as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return to_me(get_user(conn, user["user_id"]) or user, settings)


@router.get("/export")
async def export_data(conn: Db, user: CurrentUser, settings: AppSettings) -> FileResponse:
    path = service.build_export_zip(conn, user["user_id"], user["business_id"], settings.upload_dir)
    return FileResponse(
        path,
        media_type="application/zip",
        filename="kanakku-data-export.zip",
        background=BackgroundTask(lambda: Path(path).unlink(missing_ok=True)),
    )


@router.delete("", status_code=204)
async def delete_account(
    body: DeleteRequest, response: Response, conn: Db, user: CurrentUser, settings: AppSettings
) -> None:
    if body.confirm_email.strip().lower() != user["email"]:
        raise HTTPException(status_code=422, detail="Type your account email to confirm")
    service.delete_account(
        conn, user["user_id"], user["business_id"], user["email"], settings.upload_dir
    )
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
