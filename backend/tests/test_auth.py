from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, signup_payload


def test_signup_sets_cookie_and_me_works(client: TestClient) -> None:
    r = client.post("/api/auth/signup", json=signup_payload())
    assert r.status_code == 201
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "samesite=lax" in r.headers["set-cookie"].lower()
    me = client.get("/api/auth/me").json()
    assert me["email"] == "a@example.com" and me["business_name"] == "Asha Traders"
    assert me["state_code"] == "33"


def test_signup_stores_consent_timestamp(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    row = client.app.state.db.execute("SELECT consent_at FROM users").fetchone()  # type: ignore[attr-defined]
    assert row["consent_at"]


def test_signup_validation(client: TestClient) -> None:
    for bad in (
        {"password": "short"},
        {"consent": False},
        {"email": "not-an-email"},
        {"state_code": "99"},
    ):
        assert client.post("/api/auth/signup", json=signup_payload(**bad)).status_code == 422


def test_duplicate_email_rejected_case_insensitive(client: TestClient) -> None:
    assert client.post("/api/auth/signup", json=signup_payload()).status_code == 201
    r = client.post("/api/auth/signup", json=signup_payload("A@Example.com"))
    assert r.status_code == 409


def test_password_is_hashed(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    h = client.app.state.db.execute("SELECT password_hash FROM users").fetchone()[0]  # type: ignore[attr-defined]
    assert h.startswith("$argon2") and PASSWORD not in h


def test_login_logout_flow(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_tampered_cookie_rejected(client: TestClient) -> None:
    client.cookies.set("kanakku_session", "garbage")
    assert client.get("/api/auth/me").status_code == 401


def test_login_rate_limit(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    client.post("/api/auth/logout")
    bad = {"email": "a@example.com", "password": "wrong-password"}
    for _ in range(5):
        assert client.post("/api/auth/login", json=bad).status_code == 401
    assert client.post("/api/auth/login", json=bad).status_code == 429
    good = {"email": "a@example.com", "password": PASSWORD}
    assert client.post("/api/auth/login", json=good).status_code == 429  # locked out
    # another email is unaffected
    assert client.post("/api/auth/login", json={**bad, "email": "b@example.com"}).status_code == 401


def test_unknown_email_is_generic_error(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever-pw"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password"


def test_states_list(client: TestClient) -> None:
    assert client.get("/api/auth/states").json()["33"] == "Tamil Nadu"
