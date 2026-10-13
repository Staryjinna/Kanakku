import io
import logging

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

from app.config import Settings
from app.llm.providers.fake import FakeProvider
from app.main import create_app
from app.security import RedactingFilter, install_log_redaction
from tests.conftest import PASSWORD, FakeReranker, signup_payload
from tests.test_bills_api import png_bytes, upload


def raw_client(settings: Settings, provider: FakeProvider) -> TestClient:
    """A client that does NOT add the CSRF header (like an attacker's page would)."""
    return TestClient(create_app(settings, provider, FakeReranker()))


# ---------- CSRF ----------


def test_signup_and_login_do_not_need_a_token(settings: Settings, provider: FakeProvider) -> None:
    with raw_client(settings, provider) as c:
        assert c.post("/api/auth/signup", json=signup_payload()).status_code == 201
        c.cookies.clear()
        assert (
            c.post(
                "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )


def test_cookie_authenticated_post_without_token_is_blocked(
    settings: Settings, provider: FakeProvider
) -> None:
    with raw_client(settings, provider) as c:
        c.post("/api/auth/signup", json=signup_payload())
        r = c.post("/api/customers", json={"name": "Evil"})
        assert r.status_code == 403 and "CSRF" in r.json()["detail"]
        assert c.get("/api/customers").json() == []  # nothing was created
        for method, path in (
            ("PATCH", "/api/account/business"),
            ("DELETE", "/api/account"),
            ("POST", "/api/auth/logout"),
        ):
            assert c.request(method, path, json={}).status_code == 403


def test_wrong_and_empty_tokens_blocked_right_token_allowed(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    body = {"name": "Ravi"}
    assert client.post("/api/customers", json=body, headers={"X-CSRF-Token": ""}).status_code == 403
    assert (
        client.post("/api/customers", json=body, headers={"X-CSRF-Token": "guess"}).status_code
        == 403
    )
    assert client.post("/api/customers", json=body).status_code == 201  # fixture adds the right one


def test_safe_methods_need_no_token(settings: Settings, provider: FakeProvider) -> None:
    with raw_client(settings, provider) as c:
        c.post("/api/auth/signup", json=signup_payload())
        assert c.get("/api/auth/me").status_code == 200
        assert c.get("/api/ledger").status_code == 200


def test_unauthenticated_post_is_401_not_csrf(settings: Settings, provider: FakeProvider) -> None:
    with raw_client(settings, provider) as c:
        assert c.post("/api/customers", json={"name": "x"}).status_code == 401


def test_origin_must_match_host(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    evil = client.post(
        "/api/customers", json={"name": "A"}, headers={"Origin": "https://evil.example"}
    )
    assert evil.status_code == 403 and "Cross-site" in evil.json()["detail"]
    same = client.post(
        "/api/customers", json={"name": "A"}, headers={"Origin": "http://testserver"}
    )
    assert same.status_code == 201


def test_cookie_flags(settings: Settings, provider: FakeProvider) -> None:
    with raw_client(settings, provider) as c:
        r = c.post("/api/auth/signup", json=signup_payload())
        cookies = {h.split("=")[0]: h.lower() for h in r.headers.get_list("set-cookie")}
        assert "httponly" in cookies["kanakku_session"]
        assert (
            "httponly" not in cookies["kanakku_csrf"] and "samesite=lax" in cookies["kanakku_csrf"]
        )


def test_logout_clears_both_cookies_and_me_restores_csrf(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    client.cookies.delete("kanakku_csrf")  # a session from before CSRF protection existed
    assert client.get("/api/auth/me").status_code == 200
    assert client.cookies.get("kanakku_csrf")
    assert client.post("/api/customers", json={"name": "ok"}).status_code == 201
    client.post("/api/auth/logout")
    assert (
        client.cookies.get("kanakku_csrf") is None and client.cookies.get("kanakku_session") is None
    )


def test_csrf_can_be_disabled_by_setting(settings: Settings, provider: FakeProvider) -> None:
    settings.csrf_enabled = False
    with raw_client(settings, provider) as c:
        c.post("/api/auth/signup", json=signup_payload())
        assert c.post("/api/customers", json={"name": "x"}).status_code == 201


# ---------- headers ----------


def test_security_headers_and_no_docs(client: TestClient) -> None:
    r = client.get("/api/health")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "SAMEORIGIN"
    assert h["referrer-policy"] == "same-origin" and h["cache-control"] == "no-store"
    csp = h["content-security-policy"]
    assert (
        "default-src 'self'" in csp
        and "object-src 'none'" in csp
        and "frame-ancestors 'self'" in csp
    )
    assert "http" not in csp.replace("'self'", "")  # no third-party origins anywhere
    assert "strict-transport-security" not in h  # only when ENV=prod
    assert client.get("/docs").status_code == 404 and client.get("/redoc").status_code == 404


def test_hsts_in_prod(tmp_path) -> None:  # type: ignore[no-untyped-def]
    s = Settings(env="prod", jwt_secret="x" * 40, db_path=":memory:", upload_dir=str(tmp_path),
                 worker_enabled=False, frontend_dist=str(tmp_path / "none"))  # fmt: skip
    with TestClient(create_app(s, FakeProvider(), FakeReranker())) as c:
        r = c.get("/api/health")
        assert "max-age=31536000" in r.headers["strict-transport-security"]
        assert c.get("/openapi.json").status_code == 404  # no API schema in prod


def test_error_responses_also_carry_headers(settings: Settings, provider: FakeProvider) -> None:
    with raw_client(settings, provider) as c:
        c.post("/api/auth/signup", json=signup_payload())
        r = c.post("/api/customers", json={"name": "x"})  # blocked by CSRF
        assert r.status_code == 403 and r.headers["x-content-type-options"] == "nosniff"


def test_uploaded_file_served_with_nosniff_and_file_csp(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = upload(client).json()["bill"]["id"]
    r = client.get(f"/api/bills/{bill_id}/file")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "object-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["content-type"] == "image/png"


# ---------- uploads ----------


def pdf_bytes(pages: int, encrypt: bool = False) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(200, 200)
    if encrypt:
        w.encrypt("secret", algorithm="RC4-128")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_upload_rejects_corrupt_and_hostile_files(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    good = png_bytes()
    r = upload(client, good[:60], "truncated.png")  # valid header, broken body
    assert r.status_code == 415 and "damaged" in r.json()["detail"]
    assert upload(client, b"%PDF-1.4 not really a pdf", "x.pdf").status_code == 415
    assert upload(client, pdf_bytes(0), "empty.pdf").status_code == 415
    assert upload(client, pdf_bytes(101), "huge.pdf").status_code == 415
    assert upload(client, b"\xff\xd8\xff\xe0" + b"\x00" * 50, "bad.jpg").status_code == 415


def test_upload_rejects_encrypted_pdf(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    r = upload(client, pdf_bytes(1, encrypt=True), "locked.pdf")
    assert r.status_code == 415 and "Password" in r.json()["detail"]


def test_upload_rejects_decompression_bomb(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    buf = io.BytesIO()
    Image.new("1", (7000, 7000)).save(buf, format="PNG")  # ~49M pixels, a few KB on disk
    assert len(buf.getvalue()) < 100_000
    r = upload(client, buf.getvalue(), "bomb.png")
    assert r.status_code == 415 and "too large" in r.json()["detail"]
    assert client.get("/api/bills").json()["total"] == 0  # nothing was stored


def test_valid_pdf_and_image_still_accepted(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    assert upload(client, png_bytes(), "ok.png").status_code == 201
    assert upload(client, pdf_bytes(2), "ok.pdf").status_code == 201


# ---------- log redaction ----------


def test_redacting_filter_cleans_message_and_args() -> None:
    logger = logging.getLogger("test.redact")
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("failed for %s phone 9876543210 mail a@b.com", "33ABCDE1234F1Z5")
    out = stream.getvalue()
    assert "[GSTIN]" in out and "[PHONE]" in out and "[EMAIL]" in out
    assert "9876543210" not in out and "a@b.com" not in out and "ABCDE1234F" not in out


def test_install_log_redaction_covers_existing_handlers() -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler(io.StringIO())
    root.addHandler(handler)
    try:
        install_log_redaction()
        assert any(isinstance(f, RedactingFilter) for f in handler.filters)
        assert logging.getLogger("httpx").level == logging.WARNING
    finally:
        root.removeHandler(handler)


def test_filter_keeps_uvicorn_access_log_format_working() -> None:
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/api/ledger?q=9876543210&m=a@b.com", "1.1", 200), None,
    )  # fmt: skip
    assert RedactingFilter().filter(record)
    line = AccessFormatter("%(levelprefix)s %(message)s").format(record)
    assert "[PHONE]" in line and "[EMAIL]" in line and "9876543210" not in line
    assert record.args is not None and len(record.args) == 5 and record.args[4] == 200
