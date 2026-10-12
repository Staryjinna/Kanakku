import sqlite3
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.auth.service import decode_token, get_user
from app.config import Settings
from app.llm.gateway import Gateway

COOKIE_NAME = "kanakku_session"


def get_db(request: Request) -> sqlite3.Connection:
    conn: sqlite3.Connection = request.app.state.db
    return conn


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_gateway(request: Request) -> Gateway:
    gateway: Gateway = request.app.state.gateway
    return gateway


Db = Annotated[sqlite3.Connection, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


def current_user(request: Request, conn: Db, settings: AppSettings) -> dict[str, Any]:
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_token(token, settings) if token else None
    user = get_user(conn, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(current_user)]


def current_business(user: CurrentUser) -> int:
    """The business_id every query must filter by."""
    return int(user["business_id"])


CurrentBusiness = Annotated[int, Depends(current_business)]
