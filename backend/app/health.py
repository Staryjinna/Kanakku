from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    try:
        request.app.state.db.execute("SELECT 1").fetchone()
        db = "ok"
    except Exception:
        db = "error"
    ollama = "ok" if await request.app.state.provider.ping() else "unreachable"
    reranker = type(request.app.state.reranker).__name__ == "CrossEncoderReranker"
    return {
        "status": "ok" if db == "ok" else "degraded",
        "db": db,
        "ollama": ollama,
        # "off" means GST search skips cross-encoder re-ranking (install the `rerank` extra)
        "reranker": "cross-encoder" if reranker else "off",
    }
