import json
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from app.jobs import queue
from tests.conftest import PASSWORD, signup_payload
from tests.helpers import add_bill, add_invoice, add_party


def signup(client: TestClient, email: str = "a@example.com") -> int:
    client.post("/api/auth/signup", json=signup_payload(email))
    return int(client.get("/api/auth/me").json()["business_id"])


def test_new_business_needs_onboarding_then_completes(client: TestClient) -> None:
    signup(client)
    assert client.get("/api/auth/me").json()["onboarding_done"] is False
    r = client.patch(
        "/api/account/business",
        json={"name": "Asha & Sons", "state_code": "33", "language": "ta", "onboarding_done": True},
    )
    assert r.status_code == 200
    me = client.get("/api/auth/me").json()
    assert (me["business_name"], me["language"], me["onboarding_done"]) == (
        "Asha & Sons",
        "ta",
        True,
    )


def test_business_update_validation(client: TestClient) -> None:
    signup(client)
    base = {"name": "X", "state_code": "33", "language": "en"}
    assert client.patch("/api/account/business", json={**base, "language": "fr"}).status_code == 422
    assert (
        client.patch("/api/account/business", json={**base, "state_code": "99"}).status_code == 422
    )
    assert (
        client.patch("/api/account/business", json={**base, "gstin": "BADGSTIN"}).status_code == 422
    )
    from tests.test_bills_validate import make_gstin

    assert (
        client.patch("/api/account/business", json={**base, "gstin": make_gstin("27")}).status_code
        == 422
    )
    ok = client.patch("/api/account/business", json={**base, "gstin": make_gstin("33").lower()})
    assert ok.status_code == 200 and ok.json()["gstin"] == make_gstin("33")
    # clearing and not touching onboarding keeps it as is
    assert client.patch("/api/account/business", json={**base, "gstin": ""}).json()["gstin"] is None


def test_account_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/account/export").status_code == 401
    assert client.patch("/api/account/business", json={}).status_code == 401
    assert (
        client.request(
            "DELETE", "/api/account", json={"confirm_email": "a@example.com"}
        ).status_code
        == 401
    )


def test_data_export_has_everything_and_no_password(client: TestClient, settings) -> None:  # type: ignore[no-untyped-def]
    biz = signup(client)
    conn = client.app.state.db  # type: ignore[attr-defined]
    folder = Path(settings.upload_dir) / str(biz)
    folder.mkdir(parents=True)
    (folder / "bill.png").write_bytes(b"IMG")
    add_bill(conn, biz, file_path=str(folder / "bill.png"))
    outside = Path(settings.upload_dir) / "other.txt"
    outside.write_text("secret")
    add_bill(conn, biz, file_path=str(outside))  # must not be exported
    cust = add_party(conn, biz, "Cust", kind="customer")
    add_invoice(conn, biz, cust)
    r = client.get("/api/account/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(BytesIO(r.content))
    assert sorted(zf.namelist()) == ["data.json", "files/bill.png"]
    data = json.loads(zf.read("data.json"))
    assert data["user"]["email"] == "a@example.com" and "password_hash" not in data["user"]
    assert (
        len(data["bills"]) == 2 and len(data["sales_invoices"]) == 1 and len(data["parties"]) == 1
    )
    assert zf.read("files/bill.png") == b"IMG"


def test_export_is_tenant_isolated(client: TestClient) -> None:
    biz = signup(client, "a@example.com")
    add_bill(client.app.state.db, biz, vendor="A only")  # type: ignore[attr-defined]
    client.post("/api/auth/logout")
    signup(client, "b@example.com")
    zf = zipfile.ZipFile(BytesIO(client.get("/api/account/export").content))
    data = json.loads(zf.read("data.json"))
    assert data["bills"] == [] and data["user"]["email"] == "b@example.com"


def test_delete_requires_matching_email(client: TestClient) -> None:
    signup(client)
    r = client.request("DELETE", "/api/account", json={"confirm_email": "wrong@example.com"})
    assert r.status_code == 422
    assert client.get("/api/auth/me").status_code == 200


def test_delete_removes_all_data_and_files_but_not_others(client: TestClient, settings) -> None:  # type: ignore[no-untyped-def]
    conn = client.app.state.db  # type: ignore[attr-defined]
    biz_b = signup(client, "b@example.com")
    add_bill(conn, biz_b, vendor="B keeps this")
    folder_b = Path(settings.upload_dir) / str(biz_b)
    folder_b.mkdir(parents=True)
    (folder_b / "b.png").write_bytes(b"B")
    client.post("/api/auth/logout")

    biz = signup(client, "a@example.com")
    folder = Path(settings.upload_dir) / str(biz)
    folder.mkdir(parents=True)
    (folder / "a.png").write_bytes(b"A")
    bill = add_bill(conn, biz, file_path=str(folder / "a.png"))
    conn.execute(
        "INSERT INTO bill_items(bill_id, description, qty, rate_paise, amount_paise) VALUES (?, 'x', 1, 1, 1)",
        (bill,),
    )
    cust = add_party(conn, biz, "Cust", kind="customer")
    inv = add_invoice(conn, biz, cust)
    conn.execute(
        "INSERT INTO followups(business_id, invoice_id, channel, draft_text, created_at) VALUES (?,?,'email','hi','2026-01-01T00:00:00Z')",
        (biz, inv),
    )
    conn.execute(
        "INSERT INTO qa_logs(business_id, question, answer, created_at) VALUES (?, 'q', 'a', '2026-01-01T00:00:00Z')",
        (biz,),
    )
    conn.execute(
        "INSERT INTO llm_calls(business_id, purpose, model, created_at) VALUES (?, 'p', 'm', '2026-01-01T00:00:00Z')",
        (biz,),
    )
    queue.enqueue(conn, "extract_bill", {"business_id": biz, "bill_id": bill})
    queue.enqueue(conn, "extract_bill", {"business_id": biz_b, "bill_id": 1})

    r = client.request("DELETE", "/api/account", json={"confirm_email": "A@Example.com"})
    assert r.status_code == 204
    for table in ("bills", "parties", "sales_invoices", "followups", "qa_logs", "llm_calls"):
        assert (
            conn.execute(f"SELECT COUNT(*) FROM {table} WHERE business_id = ?", (biz,)).fetchone()[
                0
            ]
            == 0
        ), table
    assert (
        conn.execute("SELECT COUNT(*) FROM bill_items WHERE bill_id = ?", (bill,)).fetchone()[0]
        == 0
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM users WHERE email = 'a@example.com'").fetchone()[0] == 0
    )
    assert conn.execute("SELECT COUNT(*) FROM businesses WHERE id = ?", (biz,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1  # only B's job remains
    assert not folder.exists()
    # logged out, cannot log back in
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 401
    # B untouched
    assert (
        conn.execute("SELECT COUNT(*) FROM bills WHERE business_id = ?", (biz_b,)).fetchone()[0]
        == 1
    )
    assert (folder_b / "b.png").exists()
    # the email can be registered again
    assert client.post("/api/auth/signup", json=signup_payload("a@example.com")).status_code == 201
