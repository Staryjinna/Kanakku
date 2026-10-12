import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.gateway import Gateway
from app.llm.providers.base import LLMError
from app.llm.providers.fake import FakeProvider
from app.llm.providers.ollama import OllamaProvider


class Item(BaseModel):
    name: str
    qty: int


def calls(conn):  # type: ignore[no-untyped-def]
    return conn.execute("SELECT * FROM llm_calls ORDER BY id").fetchall()


async def test_chat_is_logged_with_redacted_preview(gateway: Gateway, conn) -> None:  # type: ignore[no-untyped-def]
    msg = [{"role": "user", "content": "Vendor 33ABCDE1234F1Z5 phone 9876543210 a@b.com"}]
    res = await gateway.chat(msg, purpose="test", business_id=None)
    assert res.text == "fake-response"
    (row,) = calls(conn)
    assert row["purpose"] == "test" and row["cache_hit"] == 0 and row["error"] is None
    preview = row["redacted_prompt_preview"]
    assert "[GSTIN]" in preview and "[PHONE]" in preview and "[EMAIL]" in preview
    assert "9876543210" not in preview and "a@b.com" not in preview


async def test_preview_truncated_to_300(gateway: Gateway, conn) -> None:  # type: ignore[no-untyped-def]
    await gateway.chat([{"role": "user", "content": "x" * 1000}], purpose="t")
    assert len(calls(conn)[0]["redacted_prompt_preview"]) == 300


async def test_cache_hit_for_deterministic_calls(gateway: Gateway, provider, conn) -> None:  # type: ignore[no-untyped-def]
    msg = [{"role": "user", "content": "hi"}]
    await gateway.chat(msg, purpose="t")
    second = await gateway.chat(msg, purpose="t")
    assert second.cache_hit and len(provider.chat_calls) == 1
    assert [r["cache_hit"] for r in calls(conn)] == [0, 1]


async def test_no_cache_for_images_or_nonzero_temperature(gateway: Gateway, provider) -> None:  # type: ignore[no-untyped-def]
    msg = [{"role": "user", "content": "hi"}]
    await gateway.chat(msg, purpose="t", images=["abc"])
    await gateway.chat(msg, purpose="t", images=["abc"])
    await gateway.chat(msg, purpose="t", temperature=0.7)
    await gateway.chat(msg, purpose="t", temperature=0.7)
    assert len(provider.chat_calls) == 4


async def test_structured_output_parsed(gateway: Gateway, provider) -> None:  # type: ignore[no-untyped-def]
    provider.push('{"name": "pen", "qty": 3}')
    res = await gateway.chat([{"role": "user", "content": "x"}], purpose="t", json_schema=Item)
    assert res.parsed == Item(name="pen", qty=3)
    assert provider.chat_calls[0]["schema"]["properties"]["qty"]


async def test_one_repair_retry(gateway: Gateway, provider) -> None:  # type: ignore[no-untyped-def]
    provider.push("not json", '{"name": "pen", "qty": 3}')
    res = await gateway.chat([{"role": "user", "content": "x"}], purpose="t", json_schema=Item)
    assert res.parsed == Item(name="pen", qty=3)
    assert len(provider.chat_calls) == 2


async def test_fails_after_single_repair(gateway: Gateway, provider, conn) -> None:  # type: ignore[no-untyped-def]
    provider.push("bad", "still bad")
    with pytest.raises(LLMError):
        await gateway.chat([{"role": "user", "content": "x"}], purpose="t", json_schema=Item)
    assert len(provider.chat_calls) == 2
    assert calls(conn)[0]["error"]


async def test_embed_logged(gateway: Gateway, conn) -> None:  # type: ignore[no-untyped-def]
    vecs = await gateway.embed(["a", "b"])
    assert len(vecs) == 2 and len(vecs[0]) == 8
    assert calls(conn)[0]["purpose"] == "embed"


def ollama(handler) -> OllamaProvider:  # type: ignore[no-untyped-def]
    client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(handler))
    return OllamaProvider("http://ollama", client=client)


async def test_ollama_chat_request_shape() -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        return httpx.Response(
            200, json={"message": {"content": "ok"}, "prompt_eval_count": 5, "eval_count": 2}
        )

    p = ollama(handler)
    res = await p.chat(
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        json_schema={"type": "object"},
        images=["IMG"],
        temperature=0,
    )
    assert (res.content, res.prompt_tokens, res.completion_tokens) == ("ok", 5, 2)
    assert seen["format"] == {"type": "object"} and seen["stream"] is False
    assert seen["messages"][0]["images"] == ["IMG"]


async def test_ollama_retries_on_connect_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.llm.providers.ollama.asyncio.sleep", lambda s: _noop())
    attempts = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    assert await ollama(handler).embed(model="m", texts=["a"]) == [[1.0]]
    assert attempts == 3


async def test_ollama_gives_up_after_retries(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("app.llm.providers.ollama.asyncio.sleep", lambda s: _noop())

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(LLMError):
        await ollama(handler).embed(model="m", texts=["a"])


async def _noop() -> None:
    return None


async def test_fake_provider_is_a_provider() -> None:
    assert await FakeProvider().ping()
