from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class StreamEvent:
    """One piece of a streamed reply. The last event carries token counts."""

    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMError(Exception):
    """Provider unreachable or returned an error."""


class Provider(Protocol):
    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        images: list[str] | None,
        temperature: float,
    ) -> ProviderResult: ...

    def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
    ) -> AsyncIterator[StreamEvent]: ...

    async def embed(self, *, model: str, texts: list[str]) -> list[list[float]]: ...

    async def ping(self) -> bool: ...
