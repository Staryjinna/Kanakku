import json
import sqlite3
from typing import Any

from app.db import utcnow_iso
from app.llm.redact import redact

MAX_ATTEMPTS = 3


def enqueue(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> int:
    now = utcnow_iso()
    cur = conn.execute(
        "INSERT INTO jobs(kind, payload_json, status, attempts, created_at, updated_at)"
        " VALUES (?, ?, 'queued', 0, ?, ?)",
        (kind, json.dumps(payload), now, now),
    )
    return int(cur.lastrowid or 0)


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row


def reset_running(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "UPDATE jobs SET status = 'queued', updated_at = ? WHERE status = 'running'",
        (utcnow_iso(),),
    )
    return cur.rowcount


def claim_next(conn: sqlite3.Connection) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE jobs SET status = 'running', attempts = attempts + 1, updated_at = ? WHERE id = ?",
        (utcnow_iso(), row["id"]),
    )
    return get_job(conn, row["id"])


def mark_done(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(
        "UPDATE jobs SET status = 'done', error = NULL, updated_at = ? WHERE id = ?",
        (utcnow_iso(), job_id),
    )


def mark_failed(conn: sqlite3.Connection, job_id: int, attempts: int, error: str) -> None:
    status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
    conn.execute(
        "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (status, redact(error)[:500], utcnow_iso(), job_id),
    )
