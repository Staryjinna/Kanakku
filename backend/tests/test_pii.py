"""Hard rule 7: no PAN, GSTIN, phone, email or account numbers in llm_calls or application logs."""

import asyncio
import logging
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.gst_qa import ingest
from app.llm.providers.base import LLMError
from app.llm.providers.fake import FakeProvider
from tests.conftest import signup_payload
from tests.helpers import add_party
from tests.pdfs import text_pdf
from tests.test_bills_api import run_worker
from tests.test_followups_api import customer, invoice
from tests.test_gst_search import COMPOSITION, write_pdf

PAN = "ABCDE1234F"
GSTIN = "33ABCDE1234F1Z5"
PHONE = "9876543210"
EMAIL = "owner.private@example.com"
ACCOUNT = "123456789012"

PATTERNS = {
    "PAN": re.compile(r"(?<![A-Z0-9])[A-Z]{5}\d{4}[A-Z](?![A-Z0-9])"),
    "GSTIN": re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]"),
    "phone": re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "account": re.compile(r"\d{9,}"),
}
PII_TEXT = (
    f"Tax invoice. Seller GSTIN {GSTIN} PAN {PAN}. Phone {PHONE}. Email {EMAIL}. "
    f"Bank account {ACCOUNT}. Total 1180 rupees, bill number INV-77, dated today."
)


def leaks(text: str | None) -> list[str]:
    return [name for name, rx in PATTERNS.items() if text and rx.search(text)]


def assert_clean(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT * FROM llm_calls").fetchall()
    assert rows, "the flows should have produced llm_calls rows"
    for row in rows:
        for column in row.keys():
            value = row[column]
            if isinstance(value, str):
                assert not leaks(value), f"{leaks(value)} leaked into llm_calls.{column}: {value!r}"
    for table, column in (("jobs", "error"), ("bills", "error")):
        for r in conn.execute(f"SELECT {column} FROM {table}"):
            assert not leaks(r[0]), f"PII in {table}.{column}: {r[0]!r}"


def test_redact_covers_every_pattern_used_here() -> None:
    from app.llm.redact import redact

    assert leaks(redact(PII_TEXT)) == []
    assert leaks(PII_TEXT) == ["PAN", "GSTIN", "phone", "email", "account"] or leaks(PII_TEXT)


@pytest.fixture
def conn_of(client: TestClient) -> sqlite3.Connection:
    return client.app.state.db  # type: ignore[attr-defined,no-any-return]


def test_no_pii_in_llm_calls_or_logs_across_all_features(
    client: TestClient,
    provider: FakeProvider,
    conn_of: sqlite3.Connection,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client.post("/api/auth/signup", json=signup_payload())

    # 1. a bill whose text contains all the PII kinds; the model's reply is invalid and also
    #    echoes PII, so the stored error text must be scrubbed too
    pdf = text_pdf([[PII_TEXT[i : i + 90] for i in range(0, len(PII_TEXT), 90)]])
    bill_id = client.post("/api/bills", files={"file": ("b.pdf", pdf, "application/pdf")}).json()[
        "bill"
    ]["id"]
    provider.push(*[f"garbage {GSTIN} {PHONE} {EMAIL} {ACCOUNT}"] * 6)
    for _ in range(3):
        run_worker(client)
    assert client.get(f"/api/bills/{bill_id}").json()["status"] == "failed"

    # 2. a GST question full of PII (goes to the embedding call and the answer prompt)
    write_pdf(tmp_path, "Composition_Guide.pdf", [COMPOSITION])
    asyncio.run(ingest.ingest_corpus(conn_of, client.app.state.gateway, tmp_path))  # type: ignore[attr-defined]
    provider.push("NOT_SUPPORTED")
    question = f"My GSTIN {GSTIN}, PAN {PAN}, call {PHONE} or {EMAIL}, account {ACCOUNT}: composition rate?"
    assert client.post("/api/gst/ask", json={"question": question}).status_code == 200

    # 3. a follow-up draft for a customer who has a phone number and email on file
    inv = invoice(client, customer(client, phone=PHONE, email=EMAIL))
    provider.push("")
    client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "whatsapp"})

    # 4. a provider failure whose message contains PII
    async def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise LLMError(f"connection failed for {EMAIL} {GSTIN}")

    provider.chat = boom  # type: ignore[method-assign,assignment]
    client.post("/api/gst/ask", json={"question": "composition scheme turnover rate"})

    assert_clean(conn_of)
    assert not leaks(caplog.text), f"PII in application logs: {leaks(caplog.text)}"


def test_error_column_is_redacted_but_still_useful(
    client: TestClient, provider: FakeProvider, conn_of: sqlite3.Connection
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    asyncio.run(_failing_call(client, provider))
    err = conn_of.execute("SELECT error FROM llm_calls WHERE error IS NOT NULL").fetchone()[0]
    assert "[EMAIL]" in err and "LLMError" in err and EMAIL not in err


async def _failing_call(client: TestClient, provider: FakeProvider) -> None:
    async def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise LLMError(f"cannot reach host for {EMAIL}")

    provider.chat = boom  # type: ignore[method-assign,assignment]
    with pytest.raises(LLMError):
        await client.app.state.gateway.chat([{"role": "user", "content": "hi"}], purpose="t")  # type: ignore[attr-defined]


def test_party_contact_details_never_enter_prompts(
    client: TestClient, provider: FakeProvider, conn_of: sqlite3.Connection
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    biz = client.get("/api/auth/me").json()["business_id"]
    add_party(conn_of, biz, "Vendor", phone=PHONE, email=EMAIL, gstin=GSTIN)
    inv = invoice(client, customer(client, phone=PHONE, email=EMAIL))
    provider.push("")
    client.post(f"/api/invoices/{inv['id']}/followups", json={"channel": "email"})
    prompts = " ".join(m["content"] for call in provider.chat_calls for m in call["messages"])
    assert not leaks(prompts)
