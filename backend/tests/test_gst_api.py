import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.gst_qa import ingest
from app.llm.providers.base import LLMError
from app.llm.providers.fake import FakeProvider
from tests.conftest import signup_payload
from tests.test_gst_search import COMPOSITION, write_pdf


def parse_sse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        event, data = block.split("\n", 1)
        out.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


async def load_corpus(client: TestClient, tmp_path: Path) -> None:
    write_pdf(tmp_path, "Composition_Guide.pdf", [COMPOSITION])
    app = client.app
    await ingest.ingest_corpus(app.state.db, app.state.gateway, tmp_path)  # type: ignore[attr-defined]


def test_requires_auth(client: TestClient) -> None:
    assert client.post("/api/gst/ask", json={"question": "hello there"}).status_code == 401
    assert client.get("/api/gst/history").status_code == 401
    assert client.get("/api/gst/documents").status_code == 401


def test_question_validation(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    assert client.post("/api/gst/ask", json={"question": "a"}).status_code == 422
    assert client.post("/api/gst/ask", json={"question": "x" * 501}).status_code == 422


async def test_ask_streams_sse(client: TestClient, provider: FakeProvider, tmp_path: Path) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    await load_corpus(client, tmp_path)
    provider.push("Composition dealers pay a fixed rate [1].")
    r = client.post("/api/gst/ask", json={"question": "composition scheme turnover rate"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    assert events[0][0] == "delta" and events[-1][0] == "done"
    done = events[-1][1]
    assert not done["refused"] and done["citations"][0]["title"] == "Composition Guide"
    assert done["answer"].endswith("Please verify with your CA before acting.")
    docs = client.get("/api/gst/documents").json()
    assert docs[0]["title"] == "Composition Guide" and docs[0]["chunks"] == 1


def test_ask_with_empty_corpus_refuses(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    events = parse_sse(
        client.post("/api/gst/ask", json={"question": "What is the GST on rice?"}).text
    )
    assert events[-1][0] == "done" and events[-1][1]["refused"]


async def test_model_down_gives_error_event(
    client: TestClient, provider: FakeProvider, tmp_path: Path
) -> None:
    client.post("/api/auth/signup", json=signup_payload())
    await load_corpus(client, tmp_path)

    async def boom(**kwargs):  # type: ignore[no-untyped-def]
        raise LLMError("down")
        yield  # pragma: no cover

    provider.chat_stream = boom  # type: ignore[method-assign,assignment]
    events = parse_sse(
        client.post("/api/gst/ask", json={"question": "composition scheme turnover"}).text
    )
    assert events[-1][0] == "error"


def test_history_is_tenant_isolated(client: TestClient) -> None:
    client.post("/api/auth/signup", json=signup_payload("a@example.com"))
    client.post("/api/gst/ask", json={"question": "A's private question"})
    assert [h["question"] for h in client.get("/api/gst/history").json()] == [
        "A's private question"
    ]
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json=signup_payload("b@example.com"))
    assert client.get("/api/gst/history").json() == []
    client.post("/api/gst/ask", json={"question": "B's question"})
    assert [h["question"] for h in client.get("/api/gst/history").json()] == ["B's question"]
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login", json={"email": "a@example.com", "password": "correct-horse-battery"}
    )
    assert [h["question"] for h in client.get("/api/gst/history").json()] == [
        "A's private question"
    ]
