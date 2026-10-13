from datetime import timedelta

from fastapi.testclient import TestClient

from app.db import today_ist
from app.llm.providers.fake import FakeProvider
from tests.conftest import signup_payload


def day(offset: int) -> str:
    return (today_ist() + timedelta(days=offset)).isoformat()


def signup(client: TestClient, email: str = "a@example.com") -> None:
    assert client.post("/api/auth/signup", json=signup_payload(email)).status_code == 201


def customer(client: TestClient, name: str = "Ravi Kumar", **extra: str) -> int:
    body = {"name": name, "phone": "98765 43210", "email": "ravi@shop.in", **extra}
    r = client.post("/api/customers", json=body)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def invoice(
    client: TestClient, cust: int, no: str = "INV-101", due: int = -10, total: int = 500000
) -> dict:  # type: ignore[type-arg]
    r = client.post(
        "/api/invoices",
        json={"customer_id": cust, "invoice_no": no, "invoice_date": day(due - 30),
              "due_date": day(due), "total_paise": total},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def good_reply(client: TestClient, inv: dict) -> str:  # type: ignore[type-arg]
    from app.followups.templates import fmt_date, fmt_inr

    return (
        f"Hello Ravi Kumar, a friendly reminder from Asha Traders: invoice {inv['invoice_no']} "
        f"for ₹{fmt_inr(inv['balance_paise'])}, due on {fmt_date(inv['due_date'])}, is pending."
    )


def test_requires_auth(client: TestClient) -> None:
    for path in ("/api/customers", "/api/invoices"):
        assert client.get(path).status_code == 401
    assert client.post("/api/invoices/1/followups", json={"channel": "email"}).status_code == 401
    assert client.post("/api/followups/1/approve").status_code == 401


def test_customer_crud_and_validation(client: TestClient) -> None:
    signup(client)
    cid = customer(client)
    assert client.get("/api/customers").json()[0]["name"] == "Ravi Kumar"
    assert client.post("/api/customers", json={"name": "X", "phone": "123"}).status_code == 422
    assert client.post("/api/customers", json={"name": "X", "email": "nope"}).status_code == 422
    assert client.post("/api/customers", json={"name": ""}).status_code == 422
    r = client.put(f"/api/customers/{cid}", json={"name": "Ravi K", "phone": None, "email": None})
    assert r.json()["name"] == "Ravi K" and r.json()["phone"] is None
    assert client.delete(f"/api/customers/{cid}").status_code == 204
    assert client.get("/api/customers").json() == []
    assert client.delete(f"/api/customers/{cid}").status_code == 404


def test_cannot_delete_customer_with_invoices(client: TestClient) -> None:
    signup(client)
    cid = customer(client)
    inv = invoice(client, cid)
    assert client.delete(f"/api/customers/{cid}").status_code == 409
    assert client.delete(f"/api/invoices/{inv['id']}").status_code == 204
    assert client.delete(f"/api/customers/{cid}").status_code == 204


def test_invoice_overdue_and_balance(client: TestClient) -> None:
    signup(client)
    cid = customer(client)
    overdue = invoice(client, cid, "A-1", due=-10)
    today_due = invoice(client, cid, "A-2", due=0)
    future = invoice(client, cid, "A-3", due=5)
    assert (overdue["overdue"], overdue["days_overdue"], overdue["balance_paise"]) == (
        True,
        10,
        500000,
    )
    assert today_due["overdue"] is False and future["overdue"] is False
    assert [i["invoice_no"] for i in client.get("/api/invoices?overdue=true").json()] == ["A-1"]
    assert len(client.get("/api/invoices?status=open").json()) == 3


def test_invoice_validation(client: TestClient) -> None:
    signup(client)
    cid = customer(client)
    base = {"customer_id": cid, "invoice_no": "X1", "invoice_date": "2026-05-01",
            "due_date": "2026-05-31", "total_paise": 1000}  # fmt: skip
    assert client.post("/api/invoices", json={**base, "due_date": "2026-04-01"}).status_code == 422
    assert client.post("/api/invoices", json={**base, "total_paise": 0}).status_code == 422
    assert client.post("/api/invoices", json={**base, "due_date": "2026-02-30"}).status_code == 422
    assert client.post("/api/invoices", json={**base, "due_date": "tomorrow"}).status_code == 422
    assert client.post("/api/invoices", json={**base, "customer_id": 999}).status_code == 404
    assert client.post("/api/invoices", json=base).status_code == 201
    assert client.post("/api/invoices", json={**base, "invoice_no": "x1"}).status_code == 409


def test_payments(client: TestClient) -> None:
    signup(client)
    inv = invoice(client, customer(client), total=100000)
    r = client.post(f"/api/invoices/{inv['id']}/pay", json={"amount_paise": 40000})
    assert (r.json()["status"], r.json()["balance_paise"]) == ("open", 60000)
    assert (
        client.post(f"/api/invoices/{inv['id']}/pay", json={"amount_paise": 70000}).status_code
        == 422
    )
    assert (
        client.post(f"/api/invoices/{inv['id']}/pay", json={"amount_paise": 0}).status_code == 422
    )
    r = client.post(f"/api/invoices/{inv['id']}/pay")  # no body = pay the rest
    assert (r.json()["status"], r.json()["balance_paise"], r.json()["overdue"]) == (
        "paid",
        0,
        False,
    )
    assert client.post(f"/api/invoices/{inv['id']}/pay").status_code == 409
    assert client.get("/api/invoices?overdue=true").json() == []
    body = {"customer_id": inv["customer_id"], "invoice_no": "N", "invoice_date": day(-40),
            "due_date": day(-10), "total_paise": 100000}  # fmt: skip
    assert client.put(f"/api/invoices/{inv['id']}", json=body).status_code == 409


def test_edit_invoice_cannot_go_below_paid(client: TestClient) -> None:
    signup(client)
    cid = customer(client)
    inv = invoice(client, cid, total=100000)
    client.post(f"/api/invoices/{inv['id']}/pay", json={"amount_paise": 60000})
    body = {"customer_id": cid, "invoice_no": "INV-101", "invoice_date": day(-40),
            "due_date": day(-10), "total_paise": 50000}  # fmt: skip
    assert client.put(f"/api/invoices/{inv['id']}", json=body).status_code == 422
    assert (
        client.put(f"/api/invoices/{inv['id']}", json={**body, "total_paise": 60000}).json()[
            "status"
        ]
        == "paid"
    )


def test_draft_approve_send_flow(client: TestClient, provider: FakeProvider) -> None:
    signup(client)
    inv = invoice(client, customer(client))
    provider.push(good_reply(client, inv))
    r = client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"})
    assert r.status_code == 201
    f = r.json()
    assert f["status"] == "draft" and f["tone"] == "gentle" and not f["used_template"]
    assert "Ravi Kumar" in f["draft_text"]
    assert f["whatsapp_url"] is None and f["mailto_url"] is None  # no links before approval
    # cannot mark sent without approval
    assert client.post(f"/api/followups/{f['id']}/sent").status_code == 409
    f2 = client.patch(
        f"/api/followups/{f['id']}", json={"draft_text": f["draft_text"] + " Thanks!"}
    ).json()
    assert f2["draft_text"].endswith("Thanks!") and f2["status"] == "draft"
    ok = client.post(f"/api/followups/{f['id']}/approve").json()
    assert ok["status"] == "approved"
    assert ok["whatsapp_url"].startswith("https://wa.me/919876543210?text=")
    assert ok["mailto_url"].startswith("mailto:ravi@shop.in?subject=")
    assert "Thanks%21" in ok["whatsapp_url"]
    # editing after approval requires approving again
    again = client.patch(
        f"/api/followups/{f['id']}", json={"draft_text": "Changed text for Ravi Kumar"}
    ).json()
    assert again["status"] == "draft" and again["whatsapp_url"] is None
    client.post(f"/api/followups/{f['id']}/approve")
    sent = client.post(f"/api/followups/{f['id']}/sent").json()
    assert sent["status"] == "sent" and sent["sent_at"]
    assert client.post(f"/api/followups/{f['id']}/approve").status_code == 409
    assert client.patch(f"/api/followups/{f['id']}", json={"draft_text": "x"}).status_code == 409
    history = client.get(f"/api/invoices/{inv['id']}/followups").json()
    assert [h["status"] for h in history] == ["sent"]
    assert client.get(f"/api/invoices/{inv['id']}").json()["reminders_sent"] == 1


def test_nothing_is_sent_or_approved_automatically(
    client: TestClient, provider: FakeProvider
) -> None:
    signup(client)
    inv = invoice(client, customer(client))
    provider.push(good_reply(client, inv))
    client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "email"})
    rows = client.app.state.db.execute("SELECT status, sent_at FROM followups").fetchall()  # type: ignore[attr-defined]
    assert [(r["status"], r["sent_at"]) for r in rows] == [("draft", None)]


def test_new_draft_supersedes_unsent_ones(client: TestClient, provider: FakeProvider) -> None:
    signup(client)
    inv = invoice(client, customer(client))
    provider.push(good_reply(client, inv), good_reply(client, inv) + " Thanks again.")
    first = client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "email"}).json()
    client.post(
        f"/api/invoices/{inv['id']}/followups", json={"channel": "email", "variation": True}
    )
    statuses = {
        h["id"]: h["status"] for h in client.get(f"/api/invoices/{inv['id']}/followups").json()
    }
    assert statuses[first["id"]] == "rejected" and list(statuses.values()).count("draft") == 1


def test_reject(client: TestClient, provider: FakeProvider) -> None:
    signup(client)
    inv = invoice(client, customer(client))
    provider.push(good_reply(client, inv))
    f = client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "email"}).json()
    assert client.post(f"/api/followups/{f['id']}/reject").json()["status"] == "rejected"
    assert client.post(f"/api/followups/{f['id']}/approve").status_code == 409


def test_draft_preconditions(client: TestClient, provider: FakeProvider) -> None:
    signup(client)
    no_contact = customer(client, "No Contact", phone="", email="")
    inv = invoice(client, no_contact, "N-1")
    assert (
        client.post(
            f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "email"}).status_code
        == 422
    )
    assert (
        client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "sms"}).status_code
        == 422
    )
    not_due = invoice(client, customer(client), "F-1", due=5)
    assert (
        client.post(
            f"/api/invoices/{not_due['id']}/followups", json={"channel": "email"}
        ).status_code
        == 409
    )
    paid = invoice(client, customer(client, "Paid P"), "P-1")
    client.post(f"/api/invoices/{paid['id']}/pay")
    assert (
        client.post(f"/api/invoices/{paid['id']}/followups", json={"channel": "email"}).status_code
        == 409
    )
    assert provider.chat_calls == []  # none of these reached the model


def test_bad_model_output_falls_back_to_template(
    client: TestClient, provider: FakeProvider
) -> None:
    signup(client)
    inv = invoice(client, customer(client))
    provider.push("Pay up or we will sue you for ₹99999", "Still wrong ₹1")
    f = client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"}).json()
    assert (
        f["used_template"] is True
        and "Ravi Kumar" in f["draft_text"]
        and "₹5,000" in f["draft_text"]
    )
    assert len(provider.chat_calls) == 2  # one call + one repair, never more


def test_tamil_business_language(client: TestClient, provider: FakeProvider) -> None:
    signup(client)
    client.patch(
        "/api/account/business", json={"name": "Asha Traders", "state_code": "33", "language": "ta"}
    )
    inv = invoice(client, customer(client))
    provider.push("", "")
    f = client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"}).json()
    assert "வணக்கம்" in f["draft_text"]
    assert "Tamil" in provider.chat_calls[0]["messages"][0]["content"]


def test_prompt_has_no_contact_details(client: TestClient, provider: FakeProvider) -> None:
    signup(client)
    inv = invoice(client, customer(client))
    provider.push(good_reply(client, inv))
    client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"})
    prompt = " ".join(m["content"] for m in provider.chat_calls[0]["messages"])
    assert "9876543210" not in prompt and "98765" not in prompt and "ravi@shop.in" not in prompt


def test_tenant_isolation(client: TestClient, provider: FakeProvider) -> None:
    signup(client, "a@example.com")
    cid = customer(client)
    inv = invoice(client, cid)
    provider.push(good_reply(client, inv))
    f = client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"}).json()
    client.post("/api/auth/logout")
    signup(client, "b@example.com")
    assert client.get("/api/customers").json() == [] and client.get("/api/invoices").json() == []
    assert client.get(f"/api/invoices/{inv['id']}").status_code == 404
    assert client.get(f"/api/invoices/{inv['id']}/followups").status_code == 404
    assert client.put(f"/api/customers/{cid}", json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/api/customers/{cid}").status_code == 404
    assert client.post(f"/api/invoices/{inv['id']}/pay").status_code == 404
    assert client.delete(f"/api/invoices/{inv['id']}").status_code == 404
    assert (
        client.post(
            f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"}
        ).status_code
        == 404
    )
    for action in ("approve", "sent", "reject"):
        assert client.post(f"/api/followups/{f['id']}/{action}").status_code == 404
    assert client.patch(f"/api/followups/{f['id']}", json={"draft_text": "x"}).status_code == 404
    # B cannot create an invoice for A's customer
    body = {
        "customer_id": cid,
        "invoice_no": "Z",
        "invoice_date": day(-40),
        "due_date": day(-10),
        "total_paise": 100,
    }
    assert client.post("/api/invoices", json=body).status_code == 404
    # and A's invoice number does not block B
    own = customer(client, "B Customer")
    assert (
        client.post(
            "/api/invoices", json={**body, "customer_id": own, "invoice_no": "INV-101"}
        ).status_code
        == 201
    )


def test_dashboard_overdue_uses_balance(client: TestClient) -> None:
    signup(client)
    cid = customer(client)
    inv = invoice(client, cid, total=100000)
    client.post(f"/api/invoices/{inv['id']}/pay", json={"amount_paise": 30000})
    invoice(client, cid, "INV-2", due=3)
    d = client.get("/api/dashboard").json()
    assert d["overdue"] == {"count": 1, "amount_paise": 70000}
