import hashlib
from collections.abc import AsyncIterator
from typing import Any

from app.llm.providers.base import ProviderResult, StreamEvent


class FakeProvider:
    """Deterministic provider for tests. Queue canned replies with `push`."""

    def __init__(self, default: str = "fake-response", dim: int = 8) -> None:
        self.default = default
        self.dim = dim
        self.replies: list[str] = []
        self.chat_calls: list[dict[str, Any]] = []
        self.embed_calls: list[list[str]] = []
        self.up = True

    def push(self, *replies: str) -> None:
        self.replies.extend(replies)

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        images: list[str] | None,
        temperature: float,
    ) -> ProviderResult:
        self.chat_calls.append(
            {"model": model, "messages": messages, "schema": json_schema, "images": images}
        )
        content = self.replies.pop(0) if self.replies else self.default
        words = sum(len(str(m["content"]).split()) for m in messages)
        return ProviderResult(content, prompt_tokens=words, completion_tokens=len(content.split()))

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        self.chat_calls.append(
            {"model": model, "messages": messages, "schema": None, "images": None}
        )
        content = self.replies.pop(0) if self.replies else self.default
        words = content.split(" ")
        for i, w in enumerate(words):
            yield StreamEvent(w if i == 0 else " " + w)
        yield StreamEvent("", sum(len(str(m["content"]).split()) for m in messages), len(words))

    async def embed(self, *, model: str, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        out: list[list[float]] = []
        for t in texts:
            digest = hashlib.sha256(t.encode()).digest()
            out.append([b / 255 for b in digest[: self.dim]])
        return out

    async def ping(self) -> bool:
        return self.up
