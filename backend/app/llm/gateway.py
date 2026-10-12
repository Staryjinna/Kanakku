"""The only entry point for AI. No other module may import a provider/AI client directly."""

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.db import utcnow_iso
from app.llm.cache import cache_get, cache_key, cache_put
from app.llm.providers.base import LLMError, Provider, ProviderResult
from app.llm.redact import redact

PREVIEW_CHARS = 300


@dataclass
class ChatResponse:
    text: str
    parsed: BaseModel | None = None
    cache_hit: bool = False


class Gateway:
    def __init__(self, provider: Provider, conn: sqlite3.Connection, settings: Settings) -> None:
        self.provider = provider
        self.conn = conn
        self.settings = settings

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        purpose: str,
        business_id: int | None = None,
        model: str | None = None,
        json_schema: type[BaseModel] | None = None,
        images: list[str] | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        model = model or (
            self.settings.llm_vision_model if images else self.settings.llm_text_model
        )
        schema = json_schema.model_json_schema() if json_schema else None
        preview = redact("\n".join(str(m.get("content", "")) for m in messages))[:PREVIEW_CHARS]
        cacheable = temperature == 0 and not images
        key = cache_key(model, messages, schema)
        start = time.monotonic()

        def log(result: ProviderResult | None, hit: bool, error: str | None) -> None:
            self._log(business_id, purpose, model, result, start, hit, error, preview)

        if cacheable:
            cached = cache_get(self.conn, key)
            if cached is not None:
                try:
                    parsed = self._parse(cached["text"], json_schema)
                except (ValidationError, ValueError):
                    parsed = None  # stale/invalid cache entry: fall through to a real call
                else:
                    log(None, True, None)
                    return ChatResponse(cached["text"], parsed, cache_hit=True)

        try:
            result = await self.provider.chat(
                model=model,
                messages=messages,
                json_schema=schema,
                images=images,
                temperature=temperature,
            )
            parsed = None
            if json_schema is not None:
                result, parsed = await self._parse_with_repair(
                    result, json_schema, model, messages, schema, images, temperature
                )
        except (LLMError, ValidationError, ValueError) as exc:
            log(None, False, type(exc).__name__ + ": " + str(exc)[:200])
            if isinstance(exc, LLMError):
                raise
            raise LLMError(f"Model returned invalid output: {exc}") from exc

        if cacheable:
            cache_put(self.conn, key, {"text": result.content})
        log(result, False, None)
        return ChatResponse(result.content, parsed)

    async def embed(
        self, texts: list[str], *, purpose: str = "embed", business_id: int | None = None
    ) -> list[list[float]]:
        model = self.settings.embed_model
        preview = redact(" | ".join(texts))[:PREVIEW_CHARS]
        start = time.monotonic()
        try:
            vectors = await self.provider.embed(model=model, texts=texts)
        except LLMError as exc:
            self._log(business_id, purpose, model, None, start, False, str(exc)[:200], preview)
            raise
        self._log(business_id, purpose, model, None, start, False, None, preview)
        return vectors

    @staticmethod
    def _parse(text: str, schema_cls: type[BaseModel] | None) -> BaseModel | None:
        if schema_cls is None:
            return None
        return schema_cls.model_validate(json.loads(text))

    async def _parse_with_repair(
        self,
        result: ProviderResult,
        schema_cls: type[BaseModel],
        model: str,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        images: list[str] | None,
        temperature: float,
    ) -> tuple[ProviderResult, BaseModel]:
        try:
            return result, schema_cls.model_validate(json.loads(result.content))
        except (ValidationError, ValueError) as first:
            repair = [
                *messages,
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": "Your reply was not valid for the required JSON schema "
                    f"({str(first)[:300]}). Reply again with only the corrected JSON.",
                },
            ]
            retry = await self.provider.chat(
                model=model,
                messages=repair,
                json_schema=schema,
                images=images,
                temperature=temperature,
            )
            return retry, schema_cls.model_validate(json.loads(retry.content))

    def _log(
        self,
        business_id: int | None,
        purpose: str,
        model: str,
        result: ProviderResult | None,
        start: float,
        cache_hit: bool,
        error: str | None,
        preview: str,
    ) -> None:
        self.conn.execute(
            "INSERT INTO llm_calls(business_id, purpose, model, prompt_tokens, completion_tokens,"
            " latency_ms, cache_hit, error, redacted_prompt_preview, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                business_id,
                purpose,
                model,
                result.prompt_tokens if result else 0,
                result.completion_tokens if result else 0,
                int((time.monotonic() - start) * 1000),
                int(cache_hit),
                redact(error) if error else None,
                preview,
                utcnow_iso(),
            ),
        )
