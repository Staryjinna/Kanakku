from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.providers.fake import FakeProvider
from app.main import create_app
from app.ratelimit import check_and_record
from tests.conftest import CsrfClient, FakeReranker, signup_payload
from tests.test_bills_api import png_bytes, upload
from tests.test_followups_api import customer, invoice


def limited_client(settings: Settings, provider: FakeProvider, limit: int) -> CsrfClient:
    settings.ai_rate_limit_per_hour = limit
    return CsrfClient(create_app(settings, provider, FakeReranker()))


def ask(c: TestClient, q: str = "What is composition scheme?"):  # type: ignore[no-untyped-def]
    return c.post("/api/gst/ask", json={"question": q})


def test_window_is_sliding(conn) -> None:  # type: ignore[no-untyped-def]
    from app.auth import service
    from tests.conftest import PASSWORD

    uid = service.signup(
        conn, email="u@x.com", password=PASSWORD, name="U", business_name="B", state_code="33"
    )
    t0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    assert [check_and_record(conn, uid, 3, t0 + timedelta(minutes=m)) for m in (0, 10, 20)] == [
        None
    ] * 3
    wait = check_and_record(conn, uid, 3, t0 + timedelta(minutes=30))
    assert (
        wait is not None and 29 * 60 <= wait <= 30 * 60 + 2
    )  # until the first hit leaves the window
    assert check_and_record(conn, uid, 3, t0 + timedelta(minutes=61)) is None  # first one expired
    assert check_and_record(conn, uid, 3, t0 + timedelta(minutes=62)) is not None
    # a blocked attempt is not recorded, so waiting works
    assert check_and_record(conn, uid, 3, t0 + timedelta(minutes=81)) is None


def test_gst_ask_is_limited_per_user(settings: Settings, provider: FakeProvider) -> None:
    with limited_client(settings, provider, 3) as c:
        c.post("/api/auth/signup", json=signup_payload("a@example.com"))
        assert [ask(c).status_code for _ in range(3)] == [200, 200, 200]
        r = ask(c)
        assert r.status_code == 429 and "limit" in r.json()["detail"]
        assert 1 <= int(r.headers["retry-after"]) <= 3601
        # non-AI endpoints are unaffected
        assert (
            c.get("/api/ledger").status_code == 200 and c.get("/api/dashboard").status_code == 200
        )
        # another user has their own allowance
        c.post("/api/auth/logout")
        c.post("/api/auth/signup", json=signup_payload("b@example.com"))
        assert ask(c).status_code == 200


def test_uploads_and_drafts_count_too(settings: Settings, provider: FakeProvider) -> None:
    with limited_client(settings, provider, 2) as c:
        c.post("/api/auth/signup", json=signup_payload())
        assert upload(c, png_bytes()).status_code == 201
        assert upload(c, png_bytes()).status_code == 201
        assert upload(c, png_bytes()).status_code == 429
        assert ask(c).status_code == 429  # one shared allowance for all AI features
        inv = invoice(c, customer(c))
        r = c.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"})
        assert r.status_code == 429


def test_limit_requires_login(settings: Settings, provider: FakeProvider) -> None:
    with limited_client(settings, provider, 1) as c:
        assert ask(c).status_code == 401
