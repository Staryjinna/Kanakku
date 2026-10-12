"""Hybrid search: FTS5 (BM25) + sqlite-vec, fused with reciprocal rank fusion, then re-ranked."""

import re
import sqlite3
from dataclasses import dataclass

from app.gst_qa.ingest import vec_blob
from app.gst_qa.rerank import Reranker
from app.llm.gateway import Gateway

TOP_EACH = 20
RRF_K = 60
RERANK_POOL = 20
FINAL_K = 5

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on", "for", "and",
    "or", "do", "does", "i", "my", "me", "we", "it", "this", "that", "with", "what", "how",
    "can", "when", "which", "who", "if", "at", "by", "from", "as", "should", "will", "have",
}  # fmt: skip


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    title: str
    page: int
    text: str
    score: float = 0.0


def fts_query(question: str) -> str | None:
    tokens = [t for t in re.findall(r"\w+", question.lower()) if t not in _STOPWORDS]
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens))


def fts_search(conn: sqlite3.Connection, question: str, limit: int = TOP_EACH) -> list[int]:
    query = fts_query(question)
    if query is None:
        return []
    rows = conn.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
        (query, limit),
    ).fetchall()
    return [int(r["rowid"]) for r in rows]


def vec_search(conn: sqlite3.Connection, vector: list[float], limit: int = TOP_EACH) -> list[int]:
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunks_vec'").fetchone()
    if not exists:
        return []
    rows = conn.execute(
        "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (vec_blob(vector), limit),
    ).fetchall()
    return [int(r["rowid"]) for r in rows]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion. Returns (id, score) best first."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def load_hits(conn: sqlite3.Connection, ids: list[int]) -> dict[int, Hit]:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT c.id, c.document_id, d.title, c.page, c.text FROM chunks c"
        f" JOIN documents d ON d.id = c.document_id WHERE c.id IN ({marks})",
        ids,
    ).fetchall()
    return {r["id"]: Hit(r["id"], r["document_id"], r["title"], r["page"], r["text"]) for r in rows}


async def search(
    conn: sqlite3.Connection,
    gateway: Gateway,
    reranker: Reranker,
    question: str,
    business_id: int | None = None,
) -> list[Hit]:
    has_chunks = conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone()
    if not has_chunks:
        return []
    (vector,) = await gateway.embed([question], purpose="gst_query", business_id=business_id)
    fused = rrf([fts_search(conn, question), vec_search(conn, vector)])[:RERANK_POOL]
    hits = load_hits(conn, [cid for cid, _ in fused])
    pool = [hits[cid] for cid, _ in fused if cid in hits]
    if not pool:
        return []
    scores = await reranker.score(question, [h.text for h in pool])
    for hit, score in zip(pool, scores, strict=True):
        hit.score = score
    pool.sort(key=lambda h: -h.score)
    return pool[:FINAL_K]
