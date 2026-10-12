import hashlib
import json
import sqlite3
from typing import Any

from app.db import utcnow_iso


def cache_key(model: str, messages: list[dict[str, Any]], schema: dict[str, Any] | None) -> str:
    blob = json.dumps([model, messages, schema], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_get(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT response_json FROM llm_cache WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    value: dict[str, Any] = json.loads(row["response_json"])
    return value


def cache_put(conn: sqlite3.Connection, key: str, response: dict[str, Any]) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache(key, response_json, created_at) VALUES (?, ?, ?)",
        (key, json.dumps(response), utcnow_iso()),
    )
