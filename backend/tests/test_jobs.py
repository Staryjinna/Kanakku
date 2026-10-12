import json

from fastapi.testclient import TestClient

from app.jobs import queue
from app.jobs.worker import Worker
from tests.conftest import signup_payload


async def test_worker_runs_job(conn) -> None:  # type: ignore[no-untyped-def]
    seen: list[dict] = []

    async def handler(payload: dict) -> None:
        seen.append(payload)

    w = Worker(conn)
    w.register("x", handler)
    job_id = queue.enqueue(conn, "x", {"a": 1})
    assert await w.run_once() is True
    assert seen == [{"a": 1}]
    assert queue.get_job(conn, job_id)["status"] == "done"
    assert await w.run_once() is False


async def test_retries_then_fails_after_three_attempts(conn) -> None:  # type: ignore[no-untyped-def]
    async def boom(payload: dict) -> None:
        raise ValueError("nope")

    w = Worker(conn)
    w.register("x", boom)
    job_id = queue.enqueue(conn, "x", {})
    await w.run_once()
    assert queue.get_job(conn, job_id)["status"] == "queued"
    await w.run_once()
    await w.run_once()
    job = queue.get_job(conn, job_id)
    assert job["status"] == "failed" and job["attempts"] == 3 and "nope" in job["error"]
    assert await w.run_once() is False


async def test_unknown_kind_fails(conn) -> None:  # type: ignore[no-untyped-def]
    job_id = queue.enqueue(conn, "missing", {})
    w = Worker(conn)
    for _ in range(3):
        await w.run_once()
    assert queue.get_job(conn, job_id)["status"] == "failed"


def test_startup_resets_running_jobs(conn) -> None:  # type: ignore[no-untyped-def]
    job_id = queue.enqueue(conn, "x", {})
    queue.claim_next(conn)
    assert queue.get_job(conn, job_id)["status"] == "running"
    assert queue.reset_running(conn) == 1
    assert queue.get_job(conn, job_id)["status"] == "queued"


def test_jobs_endpoint_is_tenant_isolated(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload("a@example.com"))
    a_biz = client.get("/api/auth/me").json()["business_id"]
    conn = client.app.state.db  # type: ignore[attr-defined]
    mine = queue.enqueue(conn, "x", {"business_id": a_biz})
    other = queue.enqueue(conn, "x", {"business_id": a_biz + 1000})
    r = client.get(f"/api/jobs/{mine}")
    assert r.status_code == 200 and r.json()["status"] == "queued"
    assert "payload_json" not in json.dumps(r.json())
    assert client.get(f"/api/jobs/{other}").status_code == 404
    assert client.get("/api/jobs/99999").status_code == 404
    client.post("/api/auth/logout")
    assert client.get(f"/api/jobs/{mine}").status_code == 401
