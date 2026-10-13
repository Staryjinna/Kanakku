import re
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.auth import service
from app.auth.deps import COOKIE_NAME, AppSettings, CurrentUser, Db
from app.config import Settings
from app.security import CSRF_COOKIE, new_csrf_token
from app.states import STATES

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v) or len(v) > 254:
        raise ValueError("Invalid email address")
    return v


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=10, max_length=200)
    name: Annotated[str, Field(min_length=1, max_length=100)]
    business_name: Annotated[str, Field(min_length=1, max_length=150)]
    state_code: str
    consent: bool

    _email = field_validator("email")(_check_email)

    @field_validator("state_code")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in STATES:
            raise ValueError("Unknown state code")
        return v

    @field_validator("consent")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the privacy policy")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    name: str
    business_id: int
    business_name: str
    state_code: str
    language: str
    gstin: str | None
    onboarding_done: bool
    is_admin: bool = False


def to_me(user: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return {
        **user,
        "onboarding_done": bool(user["onboarding_done"]),
        "is_admin": user["email"] in settings.admin_email_set,
    }


def _set_csrf_cookie(response: Response, settings: Settings) -> None:
    # readable by the page's JS on purpose: it echoes this value in the X-CSRF-Token header
    response.set_cookie(
        CSRF_COOKIE,
        new_csrf_token(),
        max_age=settings.jwt_expiry_days * 86400,
        httponly=False,
        samesite="lax",
        secure=settings.is_prod,
        path="/",
    )


def _set_cookie(response: Response, user_id: int, settings: AppSettings) -> None:
    _set_csrf_cookie(response, settings)
    response.set_cookie(
        COOKIE_NAME,
        service.create_token(user_id, settings),
        max_age=settings.jwt_expiry_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.is_prod,
        path="/",
    )


@router.get("/states")
async def states() -> dict[str, str]:
    return STATES


@router.post("/signup", response_model=MeResponse, status_code=201)
async def signup(body: SignupRequest, response: Response, conn: Db, settings: AppSettings):  # type: ignore[no-untyped-def]
    try:
        user_id = service.signup(
            conn,
            email=body.email,
            password=body.password,
            name=body.name,
            business_name=body.business_name,
            state_code=body.state_code,
        )
    except service.EmailTaken:
        raise HTTPException(status_code=409, detail="Email already registered") from None
    _set_cookie(response, user_id, settings)
    return to_me(service.get_user(conn, user_id) or {}, settings)


@router.post("/login", response_model=MeResponse)
async def login(body: LoginRequest, response: Response, conn: Db, settings: AppSettings):  # type: ignore[no-untyped-def]
    try:
        user_id = service.login(conn, email=body.email, password=body.password)
    except service.RateLimited:
        raise HTTPException(
            status_code=429, detail="Too many failed attempts. Try again in 15 minutes."
        ) from None
    except service.InvalidCredentials:
        raise HTTPException(status_code=401, detail="Invalid email or password") from None
    _set_cookie(response, user_id, settings)
    return to_me(service.get_user(conn, user_id) or {}, settings)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, settings: AppSettings, request: Request, response: Response):  # type: ignore[no-untyped-def]
    if CSRF_COOKIE not in request.cookies:  # sessions that predate CSRF protection
        _set_csrf_cookie(response, settings)
    return to_me(user, settings)
