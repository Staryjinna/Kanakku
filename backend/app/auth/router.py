import re
from typing import Annotated

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from app.auth import service
from app.auth.deps import COOKIE_NAME, AppSettings, CurrentUser, Db
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


def _set_cookie(response: Response, user_id: int, settings: AppSettings) -> None:
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
    return service.get_user(conn, user_id)


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
    return service.get_user(conn, user_id)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser):  # type: ignore[no-untyped-def]
    return user
