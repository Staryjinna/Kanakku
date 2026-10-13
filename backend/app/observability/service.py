import math
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any


def percentile(values: list[int], pct: float) -> int | None:
    """Nearest-rank percentile (pct in 0-100). None for no data."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def metrics(
    conn: sqlite3.Connection, days: int = 14, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=days - 1)).strftime("%Y-%m-%dT00:00:00Z")
    rows = conn.execute(
        "SELECT purpose, model, prompt_tokens, completion_tokens, latency_ms, cache_hit, error,"
        " created_at FROM llm_calls WHERE created_at >= ? ORDER BY id",
        (since,),
    ).fetchall()
    # latency of real model calls only: cache hits and failures would skew it
    real = [r["latency_ms"] for r in rows if not r["cache_hit"] and not r["error"]]
    per_day = {
        (now - timedelta(days=i)).strftime("%Y-%m-%d"): {"calls": 0, "errors": 0}
        for i in range(days - 1, -1, -1)
    }
    by_purpose: dict[str, dict[str, Any]] = {}
    for r in rows:
        day = per_day.get(r["created_at"][:10])
        if day is not None:
            day["calls"] += 1
            day["errors"] += 1 if r["error"] else 0
        p = by_purpose.setdefault(
            r["purpose"],
            {"purpose": r["purpose"], "calls": 0, "errors": 0, "cache_hits": 0, "lat": []},
        )
        p["calls"] += 1
        p["errors"] += 1 if r["error"] else 0
        p["cache_hits"] += r["cache_hit"]
        if not r["cache_hit"] and not r["error"]:
            p["lat"].append(r["latency_ms"])
    errors = sum(1 for r in rows if r["error"])
    hits = sum(r["cache_hit"] for r in rows)
    recent_errors = [
        {
            "created_at": r["created_at"],
            "purpose": r["purpose"],
            "model": r["model"],
            "error": r["error"],
        }
        for r in reversed(rows)
        if r["error"]
    ][:10]
    jobs = {
        r["status"]: r["n"]
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
    }
    return {
        "window_days": days,
        "totals": {
            "calls": len(rows),
            "errors": errors,
            "error_rate": _rate(errors, len(rows)),
            "cache_hits": hits,
            "cache_hit_rate": _rate(hits, len(rows)),
            "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "completion_tokens": sum(r["completion_tokens"] for r in rows),
        },
        "latency_ms": {"p50": percentile(real, 50), "p95": percentile(real, 95)},
        "per_day": [{"date": d, **v} for d, v in per_day.items()],
        "by_purpose": sorted(
            (
                {
                    "purpose": p["purpose"],
                    "calls": p["calls"],
                    "errors": p["errors"],
                    "cache_hits": p["cache_hits"],
                    "p50_ms": percentile(p["lat"], 50),
                    "p95_ms": percentile(p["lat"], 95),
                }
                for p in by_purpose.values()
            ),
            key=lambda x: -x["calls"],
        ),
        "recent_errors": recent_errors,
        "jobs": {k: jobs.get(k, 0) for k in ("queued", "running", "failed", "done")},
    }
