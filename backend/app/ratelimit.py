"""Per-user rate limit for endpoints that call the AI model (sliding one-hour window in SQLite)."""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException

from app.auth.deps import AppSettings, CurrentUser, Db

WINDOW = timedelta(hours=1)
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def check_and_record(
    conn: sqlite3.Connection, user_id: int, limit: int, now: datetime | None = None
) -> int | None:
    """Record a hit. Returns None if allowed, else the seconds until the user may try again."""
    now = now or datetime.now(UTC)
    since = (now - WINDOW).strftime(_FMT)
    conn.execute("DELETE FROM rate_limit_hits WHERE hit_at < ?", (since,))
    rows = conn.execute(
        "SELECT hit_at FROM rate_limit_hits WHERE user_id = ? ORDER BY hit_at LIMIT ?",
        (user_id, limit),
    ).fetchall()
    if len(rows) >= limit:
        oldest = datetime.strptime(rows[0]["hit_at"], _FMT).replace(tzinfo=UTC)
        return max(1, int((oldest + WINDOW - now).total_seconds()) + 1)
    conn.execute(
        "INSERT INTO rate_limit_hits(user_id, hit_at) VALUES (?, ?)", (user_id, now.strftime(_FMT))
    )
    return None


def ai_rate_limit(user: CurrentUser, conn: Db, settings: AppSettings) -> None:
    retry_after = check_and_record(conn, user["user_id"], settings.ai_rate_limit_per_hour)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=f"You have reached the limit of {settings.ai_rate_limit_per_hour} AI requests "
            "per hour. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


AiLimit = Annotated[None, Depends(ai_rate_limit)]
