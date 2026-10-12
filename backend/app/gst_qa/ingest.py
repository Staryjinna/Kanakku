"""Load GST PDFs into the search index (documents, chunks, FTS5, sqlite-vec)."""

import hashlib
import json
import logging
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.db import tx, utcnow_iso
from app.gst_qa.chunk import Chunk, chunk_pages
from app.llm.gateway import Gateway

logger = logging.getLogger(__name__)

EMBED_BATCH = 16


class IngestError(Exception):
    pass


@dataclass
class IngestResult:
    path: str
    status: str  # "ingested" | "skipped" | "empty"
    chunks: int = 0


def vec_blob(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_pages(path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(path))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM gst_meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def reset_index(conn: sqlite3.Connection) -> None:
    with tx(conn):
        conn.execute("DROP TABLE IF EXISTS chunks_vec")
        conn.execute("DELETE FROM chunks_fts")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM gst_meta")


def _ensure_vec_table(conn: sqlite3.Connection, model: str, dim: int) -> None:
    stored_model, stored_dim = _meta_get(conn, "embed_model"), _meta_get(conn, "embed_dim")
    if stored_model is None:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(embedding float[{dim}])"
        )
        conn.execute(
            "INSERT OR REPLACE INTO gst_meta(key, value) VALUES ('embed_model', ?)", (model,)
        )
        conn.execute(
            "INSERT OR REPLACE INTO gst_meta(key, value) VALUES ('embed_dim', ?)", (str(dim),)
        )
    elif stored_model != model or stored_dim != str(dim):
        raise IngestError(
            f"The index was built with embedding model '{stored_model}' but EMBED_MODEL is "
            f"'{model}'. Re-run ingest with --reset to rebuild it."
        )


async def _embed_all(gateway: Gateway, chunks: list[Chunk]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = [c.text for c in chunks[i : i + EMBED_BATCH]]
        vectors.extend(await gateway.embed(batch, purpose="gst_ingest"))
    if len(vectors) != len(chunks):
        raise IngestError("Embedding service returned the wrong number of vectors")
    return vectors


def _sidecar(path: Path) -> dict[str, str]:
    meta = path.with_suffix(".meta.json")
    if meta.exists():
        data = json.loads(meta.read_text())
        return {k: str(v) for k, v in data.items() if k in ("title", "source_url")}
    return {}


async def ingest_file(conn: sqlite3.Connection, gateway: Gateway, path: Path) -> IngestResult:
    digest = file_hash(path)
    if conn.execute("SELECT 1 FROM documents WHERE file_hash = ?", (digest,)).fetchone():
        return IngestResult(path.name, "skipped")
    chunks = chunk_pages(read_pages(path))
    if not chunks:
        return IngestResult(path.name, "empty")
    vectors = await _embed_all(gateway, chunks)
    meta = _sidecar(path)
    title = meta.get("title") or path.stem.replace("_", " ").replace("-", " ").strip()
    with tx(conn):
        _ensure_vec_table(conn, gateway.settings.embed_model, len(vectors[0]))
        cur = conn.execute(
            "INSERT INTO documents(title, source_url, file_path, file_hash, ingested_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (title, meta.get("source_url"), str(path), digest, utcnow_iso()),
        )
        doc_id = int(cur.lastrowid or 0)
        for chunk, vector in zip(chunks, vectors, strict=True):
            cid = int(
                conn.execute(
                    "INSERT INTO chunks(document_id, page, ordinal, text) VALUES (?, ?, ?, ?)",
                    (doc_id, chunk.page, chunk.ordinal, chunk.text),
                ).lastrowid
                or 0
            )
            conn.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)", (cid, chunk.text))
            conn.execute(
                "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)", (cid, vec_blob(vector))
            )
    return IngestResult(path.name, "ingested", len(chunks))


async def ingest_corpus(
    conn: sqlite3.Connection, gateway: Gateway, folder: Path
) -> list[IngestResult]:
    results: list[IngestResult] = []
    for path in sorted(folder.glob("*.pdf")):
        try:
            results.append(await ingest_file(conn, gateway, path))
        except IngestError:
            raise
        except Exception as exc:
            logger.warning("could not ingest %s: %s", path.name, type(exc).__name__)
            results.append(IngestResult(path.name, f"failed: {type(exc).__name__}"))
    return results
