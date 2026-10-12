import asyncio
import io
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient
from PIL import Image

from app.llm.providers.fake import FakeProvider
from tests.conftest import signup_payload
from tests.test_bills_validate import make_gstin


def png_bytes(color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (200, 120), color).save(buf, format="PNG")
    return buf.getvalue()


def extraction(**over: object) -> str:
    base: dict[str, object] = {
        "vendor_name": "Sri Murugan Traders",
        "vendor_gstin": make_gstin("33"),
        "bill_no": "INV-101",
        "bill_date": (date.today() - timedelta(days=10)).isoformat(),
        "items": [
            {
                "description": "Rice 25kg",
                "hsn": "1006",
                "qty": 2,
                "rate": 500,
                "gst_rate": 18,
                "amount": 1000,
            }
        ],
        "taxable_value": 1000,
        "cgst": 90,
        "sgst": 90,
        "igst": 0,
        "total": 1180,
        "confidence": {"total": "high", "bill_no": "low"},
    }
    base.update(over)
    return json.dumps(base)


def run_worker(client: TestClient) -> None:
    asyncio.run(client.app.state.worker.run_once())  # type: ignore[attr-defined]


def upload(client: TestClient, data: bytes | None = None, name: str = "bill.png"):  # type: ignore[no-untyped-def]
    return client.post("/api/bills", files={"file": (name, data or png_bytes(), "image/png")})


def login_new(client: TestClient, email: str) -> None:
    client.post("/api/auth/logout")
    assert client.post("/api/auth/signup", json=signup_payload(email)).status_code == 201


def process(client: TestClient, provider: FakeProvider, ext: str | None = None) -> int:
    provider.push(ext or extraction(), '{"category": "stock purchase"}')
    bill_id = upload(client).json()["bill"]["id"]
    run_worker(client)
    return int(bill_id)


def test_requires_auth(client: TestClient) -> None:
    assert client.get("/api/bills").status_code == 401
    assert upload(client).status_code == 401


def test_upload_extract_review_confirm(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    provider.push(extraction(), '{"category": "stock purchase"}')
    r = upload(client)
    assert r.status_code == 201
    body = r.json()
    assert body["bill"]["status"] == "processing"
    job_id = body["job_id"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "queued"

    run_worker(client)
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "done"
    bill = client.get(f"/api/bills/{body['bill']['id']}").json()
    assert bill["status"] == "needs_review"
    assert bill["total_paise"] == 118000 and bill["cgst_paise"] == 9000
    assert bill["category"] == "stock purchase"
    assert bill["items"][0]["amount_paise"] == 100000
    assert bill["issues"] == []
    assert "bill_no" in bill["low_confidence"]
    # the vision model got the image
    assert provider.chat_calls[0]["images"]

    r = client.post(f"/api/bills/{bill['id']}/confirm")
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert r.json()["confirmed_at"]
    conn = client.app.state.db  # type: ignore[attr-defined]
    vendors = conn.execute("SELECT name, gstin FROM parties WHERE kind='vendor'").fetchall()
    assert len(vendors) == 1 and vendors[0]["name"] == "Sri Murugan Traders"


def test_validation_issues_reported(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = process(client, provider, extraction(total=1500, igst=50))
    bill = client.get(f"/api/bills/{bill_id}").json()
    codes = {i["code"] for i in bill["issues"]}
    assert {"totals_mismatch", "tax_split"} <= codes


def test_confirm_blocked_by_errors_unless_override(
    client: TestClient, provider: FakeProvider
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = process(client, provider, extraction(total=1500))
    r = client.post(f"/api/bills/{bill_id}/confirm")
    assert r.status_code == 422
    assert any(i["code"] == "totals_mismatch" for i in r.json()["detail"]["issues"])
    assert client.get(f"/api/bills/{bill_id}").json()["status"] == "needs_review"
    r = client.post(f"/api/bills/{bill_id}/confirm", json={"override": True})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"


def test_edit_then_confirm_revalidates(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = process(client, provider, extraction(total=1500))
    bill = client.get(f"/api/bills/{bill_id}").json()
    bill["total_paise"] = 118000
    r = client.patch(f"/api/bills/{bill_id}", json=bill)
    assert r.status_code == 200 and r.json()["issues"] == []
    assert client.post(f"/api/bills/{bill_id}/confirm").status_code == 200
    # confirmed bills are frozen
    assert client.patch(f"/api/bills/{bill_id}", json=bill).status_code == 409
    assert client.post(f"/api/bills/{bill_id}/confirm").status_code == 409


def test_vendor_matched_not_duplicated(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    for _ in range(2):
        bill_id = process(client, provider)
        client.post(f"/api/bills/{bill_id}/confirm")
    conn = client.app.state.db  # type: ignore[attr-defined]
    assert conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0] == 1


def test_failed_extraction_marks_bill_failed_and_can_retry(
    client: TestClient, provider: FakeProvider
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    provider.push("bad", "bad", "bad", "bad", "bad", "bad")  # 3 attempts x (reply + repair)
    bill_id = upload(client).json()["bill"]["id"]
    for _ in range(3):
        run_worker(client)
    bill = client.get(f"/api/bills/{bill_id}").json()
    assert bill["status"] == "failed" and bill["error"]
    r = client.post(f"/api/bills/{bill_id}/retry")
    assert r.status_code == 200
    provider.push(extraction(), '{"category": "rent"}')
    run_worker(client)
    assert client.get(f"/api/bills/{bill_id}").json()["status"] == "needs_review"


def test_manual_entry_on_failed_bill(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = upload(client).json()["bill"]["id"]
    client.app.state.db.execute(  # type: ignore[attr-defined]
        "UPDATE bills SET status='failed', error='x' WHERE id=?", (bill_id,)
    )
    r = client.patch(f"/api/bills/{bill_id}", json={"vendor_name": "Hand Entry", "items": []})
    assert r.status_code == 200 and r.json()["status"] == "needs_review"


def test_upload_rejects_bad_files(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    assert upload(client, b"not an image at all", "evil.png").status_code == 415
    assert upload(client, b"<?php echo 1;", "a.jpg").status_code == 415
    big = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 10)
    assert upload(client, big, "big.pdf").status_code == 413


def test_upload_stored_under_sniffed_extension_and_business_folder(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = upload(client, png_bytes(), "../../etc/passwd.exe").json()["bill"]["id"]
    row = client.app.state.db.execute(  # type: ignore[attr-defined]
        "SELECT file_path FROM bills WHERE id=?", (bill_id,)
    ).fetchone()
    assert row["file_path"].endswith(".png")
    assert f"/uploads/{client.get('/api/auth/me').json()['business_id']}/" in row["file_path"]
    r = client.get(f"/api/bills/{bill_id}/file")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_file_path_traversal_blocked(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    bill_id = upload(client).json()["bill"]["id"]
    client.app.state.db.execute(  # type: ignore[attr-defined]
        "UPDATE bills SET file_path='/etc/passwd' WHERE id=?", (bill_id,)
    )
    assert client.get(f"/api/bills/{bill_id}/file").status_code == 404


def test_tenant_isolation(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload("a@example.com"))
    a_bill = process(client, provider)
    login_new(client, "b@example.com")
    assert client.get("/api/bills").json() == {"total": 0, "bills": []}
    assert client.get(f"/api/bills/{a_bill}").status_code == 404
    assert client.get(f"/api/bills/{a_bill}/file").status_code == 404
    assert client.patch(f"/api/bills/{a_bill}", json={"items": []}).status_code == 404
    assert client.post(f"/api/bills/{a_bill}/confirm").status_code == 404
    assert client.post(f"/api/bills/{a_bill}/retry").status_code == 404
    # B's own upload is invisible to A and B cannot see A's job
    b_job = upload(client).json()["job_id"]
    assert client.get(f"/api/jobs/{b_job}").status_code == 200
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"}
    )
    assert client.get(f"/api/jobs/{b_job}").status_code == 404
    assert client.get("/api/bills").json()["total"] == 1


def test_list_filter_and_pagination(client: TestClient, provider: FakeProvider) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    ids = [process(client, provider) for _ in range(3)]
    client.post(f"/api/bills/{ids[0]}/confirm")
    assert client.get("/api/bills?status=confirmed").json()["total"] == 1
    page = client.get("/api/bills?limit=2&offset=0").json()
    assert page["total"] == 3 and [b["id"] for b in page["bills"]] == [ids[2], ids[1]]
    assert client.get("/api/bills?status=bogus").status_code == 422
