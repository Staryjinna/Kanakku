import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.providers.base import LLMError, ProviderResult, StreamEvent

RETRIES = 2


class OllamaProvider:
    def __init__(
        self, base_url: str, timeout_s: float = 180.0, client: httpx.AsyncClient | None = None
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_s)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                resp = await self._client.post(path, json=body)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return data
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last = exc
                if attempt < RETRIES:
                    await asyncio.sleep(0.5 * 2**attempt)
            except (httpx.HTTPError, ValueError) as exc:
                raise LLMError(f"Ollama request failed: {exc}") from exc
        raise LLMError(f"Ollama unreachable: {last}")

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        images: list[str] | None,
        temperature: float,
    ) -> ProviderResult:
        msgs = [dict(m) for m in messages]
        if images:
            # Attach base64 images to the last user message.
            for m in reversed(msgs):
                if m["role"] == "user":
                    m["images"] = images
                    break
        body: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_schema is not None:
            body["format"] = json_schema
        data = await self._post("/api/chat", body)
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError("Unexpected Ollama chat response") from exc
        return ProviderResult(
            content=content,
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        for attempt in range(RETRIES + 1):
            try:
                async with self._client.stream("POST", "/api/chat", json=body) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        text = (data.get("message") or {}).get("content", "")
                        if data.get("done"):
                            yield StreamEvent(
                                text,
                                int(data.get("prompt_eval_count", 0)),
                                int(data.get("eval_count", 0)),
                            )
                        elif text:
                            yield StreamEvent(text)
                return
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt == RETRIES:
                    raise LLMError(f"Ollama unreachable: {exc}") from exc
                await asyncio.sleep(0.5 * 2**attempt)
            except (httpx.HTTPError, ValueError) as exc:
                raise LLMError(f"Ollama request failed: {exc}") from exc

    async def embed(self, *, model: str, texts: list[str]) -> list[list[float]]:
        data = await self._post("/api/embed", {"model": model, "input": texts})
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise LLMError("Unexpected Ollama embed response")
        return embeddings

    async def ping(self) -> bool:
        try:
            resp = await self._client.get("/api/tags", timeout=2.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
