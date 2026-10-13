from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.providers.fake import FakeProvider
from app.main import create_app
from app.observability.service import metrics, percentile
from tests.conftest import CsrfClient, FakeReranker, signup_payload

NOW = datetime(2026, 6, 15, 10, 0, 0, tzinfo=UTC)


def call(conn, purpose, latency, day=0, cache=0, error=None, tokens=(10, 5)) -> None:  # type: ignore[no-untyped-def]
    ts = (NOW - timedelta(days=day)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO llm_calls(purpose, model, prompt_tokens, completion_tokens, latency_ms,"
        " cache_hit, error, created_at) VALUES (?, 'm', ?, ?, ?, ?, ?, ?)",
        (purpose, tokens[0], tokens[1], latency, cache, error, ts),
    )


def test_percentile_nearest_rank() -> None:
    assert percentile([], 50) is None
    assert percentile([7], 95) == 7
    data = list(range(1, 101))
    assert (
        percentile(data, 50) == 50 and percentile(data, 95) == 95 and percentile(data, 100) == 100
    )
    assert percentile([5, 1, 3], 50) == 3  # unsorted input


def test_metrics_aggregation(conn) -> None:  # type: ignore[no-untyped-def]
    for ms in (100, 200, 300, 400):
        call(conn, "bill_extract", ms)
    call(conn, "bill_extract", 5, cache=1)  # cache hits and errors are not latency samples
    call(conn, "gst_answer", 1000, day=2)
    call(conn, "gst_answer", 50, day=2, error="LLMError: down")
    call(conn, "old", 1, day=30)  # outside the 14-day window
    m = metrics(conn, 14, NOW)
    t = m["totals"]
    assert (t["calls"], t["errors"], t["cache_hits"]) == (7, 1, 1)
    assert t["error_rate"] == round(1 / 7, 4) and t["cache_hit_rate"] == round(1 / 7, 4)
    assert t["prompt_tokens"] == 70 and t["completion_tokens"] == 35
    assert m["latency_ms"] == {"p50": 300, "p95": 1000}
    days = {d["date"]: d for d in m["per_day"]}
    assert len(m["per_day"]) == 14 and m["per_day"][-1]["date"] == "2026-06-15"
    assert days["2026-06-15"]["calls"] == 5 and days["2026-06-13"] == {
        "date": "2026-06-13",
        "calls": 2,
        "errors": 1,
    }
    assert days["2026-06-14"]["calls"] == 0  # empty days are present
    bp = {p["purpose"]: p for p in m["by_purpose"]}
    assert bp["bill_extract"]["calls"] == 5 and bp["bill_extract"]["cache_hits"] == 1
    assert bp["bill_extract"]["p50_ms"] == 200 and bp["gst_answer"]["errors"] == 1
    assert "old" not in bp and m["by_purpose"][0]["purpose"] == "bill_extract"
    assert m["recent_errors"][0]["error"] == "LLMError: down"


def test_metrics_empty_and_jobs(conn) -> None:  # type: ignore[no-untyped-def]
    from app.jobs import queue

    queue.enqueue(conn, "x", {})
    m = metrics(conn, 7, NOW)
    assert m["totals"]["calls"] == 0 and m["latency_ms"] == {"p50": None, "p95": None}
    assert m["totals"]["error_rate"] == 0.0 and m["jobs"]["queued"] == 1


def admin_client(settings: Settings, provider: FakeProvider) -> CsrfClient:
    settings.admin_emails = "Admin@Example.com, other@example.com"
    return CsrfClient(create_app(settings, provider, FakeReranker()))


def test_metrics_endpoint_is_admin_only(settings: Settings, provider: FakeProvider) -> None:
    with admin_client(settings, provider) as c:
        assert c.get("/api/admin/metrics").status_code == 401
        c.post("/api/auth/signup", json=signup_payload("user@example.com"))
        assert c.get("/api/admin/metrics").status_code == 403
        assert c.get("/api/auth/me").json()["is_admin"] is False
        c.post("/api/auth/logout")
        c.post("/api/auth/signup", json=signup_payload("admin@example.com"))
        assert c.get("/api/auth/me").json()["is_admin"] is True
        r = c.get("/api/admin/metrics?days=3")
        assert r.status_code == 200 and len(r.json()["per_day"]) == 3
        assert c.get("/api/admin/metrics?days=0").status_code == 422
        assert c.get("/api/admin/metrics?days=500").status_code == 422


def test_nobody_is_admin_by_default(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    assert client.get("/api/admin/metrics").status_code == 403
