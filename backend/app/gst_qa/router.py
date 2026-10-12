import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.deps import CurrentBusiness, Db
from app.gst_qa import answer
from app.gst_qa.rerank import Reranker
from app.llm.gateway import Gateway
from app.llm.providers.base import LLMError

router = APIRouter(prefix="/api/gst", tags=["gst"])


def get_gateway(request: Request) -> Gateway:
    gateway: Gateway = request.app.state.gateway
    return gateway


def get_reranker(request: Request) -> Reranker:
    reranker: Reranker = request.app.state.reranker
    return reranker


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=answer.MAX_QUESTION_CHARS)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/ask")
async def ask(
    body: AskRequest,
    conn: Db,
    business_id: CurrentBusiness,
    gateway: Annotated[Gateway, Depends(get_gateway)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        try:
            async for ev in answer.stream_answer(
                conn, gateway, reranker, body.question, business_id
            ):
                yield _sse(ev.type, ev.data)
        except LLMError:
            yield _sse("error", {"detail": "The AI model is not available right now. Try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/documents")
async def documents(conn: Db, _: CurrentBusiness) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT d.id, d.title, d.source_url, d.ingested_at,"
        " (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks"
        " FROM documents d ORDER BY d.title"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/history")
async def history(conn: Db, business_id: CurrentBusiness) -> list[dict[str, Any]]:
    return answer.history(conn, business_id)
