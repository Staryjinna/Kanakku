"""Local cross-encoder re-ranking (sentence-transformers). Optional install: `.[rerank]`."""

import asyncio
import logging
from typing import Any, Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    async def score(self, query: str, passages: list[str]) -> list[float]: ...


class NoopReranker:
    """Keeps the fused (RRF) order. Used when the cross-encoder is not available."""

    async def score(self, query: str, passages: list[str]) -> list[float]:
        n = len(passages)
        return [float(n - i) for i in range(n)]


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def _predict(self, query: str, passages: list[str]) -> list[float]:
        scores = self._load().predict([(query, p) for p in passages])
        return [float(s) for s in scores]

    async def score(self, query: str, passages: list[str]) -> list[float]:
        # Blocking CPU work: keep it off the event loop. Falls back to RRF order on failure.
        try:
            return await asyncio.to_thread(self._predict, query, passages)
        except Exception as exc:
            logger.warning("reranker unavailable (%s); using fused order", type(exc).__name__)
            return await NoopReranker().score(query, passages)


def get_reranker(settings: Settings) -> Reranker:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        logger.warning("sentence-transformers not installed; GST search skips re-ranking")
        return NoopReranker()
    return CrossEncoderReranker(settings.rerank_model)
