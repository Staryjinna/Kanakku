import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import Settings
from app.db import tx, utcnow_iso

MAX_FAILED_LOGINS = 5
LOGIN_WINDOW = timedelta(minutes=15)

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


class EmailTaken(Exception):
    pass


class RateLimited(Exception):
    pass


class InvalidCredentials(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expiry_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str, settings: Settings) -> int | None:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def signup(
    conn: sqlite3.Connection,
    *,
    email: str,
    password: str,
    name: str,
    business_name: str,
    state_code: str,
) -> int:
    email = email.strip().lower()
    now = utcnow_iso()
    pw_hash = hash_password(password)
    try:
        with tx(conn):
            cur = conn.execute(
                "INSERT INTO users(email, password_hash, name, consent_at, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (email, pw_hash, name.strip(), now, now),
            )
            user_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO businesses(owner_user_id, name, state_code, created_at)"
                " VALUES (?, ?, ?, ?)",
                (user_id, business_name.strip(), state_code, now),
            )
    except sqlite3.IntegrityError as exc:
        raise EmailTaken from exc
    return user_id


def _recent_failures(conn: sqlite3.Connection, email: str) -> int:
    since = (datetime.now(UTC) - LOGIN_WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM login_attempts"
        " WHERE email = ? AND success = 0 AND attempted_at >= ?",
        (email, since),
    ).fetchone()
    return int(row["n"])


def login(conn: sqlite3.Connection, *, email: str, password: str) -> int:
    email = email.strip().lower()
    if _recent_failures(conn, email) >= MAX_FAILED_LOGINS:
        raise RateLimited
    row = conn.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    ok = verify_password(row["password_hash"] if row else _DUMMY_HASH, password)
    ok = ok and row is not None
    conn.execute(
        "INSERT INTO login_attempts(email, success, attempted_at) VALUES (?, ?, ?)",
        (email, int(ok), utcnow_iso()),
    )
    if not ok:
        raise InvalidCredentials
    conn.execute("DELETE FROM login_attempts WHERE email = ? AND success = 0", (email,))
    return int(row["id"])


def get_user(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT u.id AS user_id, u.email, u.name, b.id AS business_id,"
        " b.name AS business_name, b.state_code, b.language, b.gstin"
        " FROM users u JOIN businesses b ON b.owner_user_id = u.id WHERE u.id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None
