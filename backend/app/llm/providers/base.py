from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ProviderResult:
    content: str
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

    async def embed(self, *, model: str, texts: list[str]) -> list[list[float]]: ...

    async def ping(self) -> bool: ...
