from pathlib import Path

import pytest

from app.gst_qa import ingest, search
from app.gst_qa.search import fts_query, rrf
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider
from tests.conftest import FakeReranker
from tests.pdfs import text_pdf

REGISTRATION = [
    "Registration under GST is mandatory when aggregate turnover exceeds the threshold limit.",
    "A supplier of goods must register once turnover crosses forty lakh rupees.",
]
COMPOSITION = [
    "The composition scheme lets small taxpayers pay tax at a fixed low rate on turnover.",
    "Composition dealers cannot collect tax from customers or claim input tax credit.",
]


def write_pdf(folder: Path, name: str, pages: list[list[str]]) -> Path:
    path = folder / name
    path.write_bytes(text_pdf(pages))
    return path


async def load(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    write_pdf(tmp_path, "Registration_Guide.pdf", [REGISTRATION])
    write_pdf(tmp_path, "Composition_Guide.pdf", [["intro page about something else"], COMPOSITION])
    await ingest.ingest_corpus(conn, gateway, tmp_path)


def test_rrf_prefers_items_in_both_lists() -> None:
    fused = rrf([[1, 2, 3], [3, 1, 4]])
    assert [i for i, _ in fused][:2] == [1, 3]
    assert dict(fused)[1] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_empty() -> None:
    assert rrf([[], []]) == []


def test_fts_query_drops_stopwords_and_quotes() -> None:
    assert fts_query("What is the GST threshold?") == '"gst" OR "threshold"'
    assert fts_query("the of a") is None
    assert fts_query('"; DROP TABLE x; --') == '"drop" OR "table" OR "x"'


async def test_ingest_and_idempotent(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    write_pdf(tmp_path, "Registration_Guide.pdf", [REGISTRATION])
    results = await ingest.ingest_corpus(conn, gateway, tmp_path)
    assert [(r.status, r.chunks) for r in results] == [("ingested", 1)]
    doc = conn.execute("SELECT * FROM documents").fetchone()
    assert doc["title"] == "Registration Guide"
    assert conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM chunks_vec").fetchone()[0] == 1
    again = await ingest.ingest_corpus(conn, gateway, tmp_path)
    assert again[0].status == "skipped"
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1


async def test_ingest_sidecar_title_and_url(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    write_pdf(tmp_path, "a.pdf", [REGISTRATION])
    (tmp_path / "a.meta.json").write_text('{"title": "CGST Act 2017", "source_url": "https://x"}')
    await ingest.ingest_corpus(conn, gateway, tmp_path)
    row = conn.execute("SELECT title, source_url FROM documents").fetchone()
    assert (row["title"], row["source_url"]) == ("CGST Act 2017", "https://x")


async def test_ingest_keeps_page_numbers(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    await load(conn, gateway, tmp_path)
    pages = conn.execute(
        "SELECT c.page FROM chunks c JOIN documents d ON d.id=c.document_id"
        " WHERE d.title='Composition Guide' ORDER BY c.page"
    ).fetchall()
    assert [r["page"] for r in pages] == [1, 2]


async def test_ingest_batches_embeddings(
    conn, gateway: Gateway, provider: FakeProvider, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    pages = [[f"page {i} unique words {i}"] for i in range(20)]
    write_pdf(tmp_path, "many.pdf", pages)
    await ingest.ingest_corpus(conn, gateway, tmp_path)
    assert [len(b) for b in provider.embed_calls] == [16, 4]


async def test_embed_model_change_requires_reset(
    conn, gateway: Gateway, settings, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    await load(conn, gateway, tmp_path)
    settings.embed_model = "other-model"
    write_pdf(tmp_path, "New_Doc.pdf", [["brand new content here"]])
    with pytest.raises(ingest.IngestError):
        await ingest.ingest_corpus(conn, gateway, tmp_path)
    ingest.reset_index(conn)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    results = await ingest.ingest_corpus(conn, gateway, tmp_path)
    assert all(r.status == "ingested" for r in results)


async def test_unreadable_pdf_does_not_stop_ingest(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    write_pdf(tmp_path, "ok.pdf", [REGISTRATION])
    results = await ingest.ingest_corpus(conn, gateway, tmp_path)
    assert results[0].status.startswith("failed") and results[1].status == "ingested"


async def test_search_finds_relevant_chunk(
    conn, gateway: Gateway, reranker: FakeReranker, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    await load(conn, gateway, tmp_path)
    hits = await search.search(conn, gateway, reranker, "composition scheme fixed rate turnover")
    assert hits and hits[0].title == "Composition Guide" and hits[0].page == 2
    assert len(hits) <= search.FINAL_K


async def test_search_empty_corpus(conn, gateway: Gateway, reranker: FakeReranker) -> None:  # type: ignore[no-untyped-def]
    assert await search.search(conn, gateway, reranker, "anything at all") == []


async def test_vec_search_orders_by_distance(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    await load(conn, gateway, tmp_path)
    rows = conn.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
    for row in rows:
        (vec,) = await gateway.embed([row["text"]])
        # a chunk's own embedding finds that chunk first
        assert search.vec_search(conn, vec)[0] == row["id"]


async def test_reranker_order_wins(conn, gateway: Gateway, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    await load(conn, gateway, tmp_path)

    class Reverse:
        async def score(self, query: str, passages: list[str]) -> list[float]:
            return [float(i) for i in range(len(passages))]

    hits = await search.search(conn, gateway, Reverse(), "composition registration turnover")
    assert hits[0].score >= hits[-1].score
