import asyncio
import importlib.util
import json
from pathlib import Path

from app.gst_qa import ingest
from app.llm.gateway import Gateway
from app.llm.providers.fake import FakeProvider
from tests.conftest import FakeReranker

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "evals" / "gst_golden.jsonl"


def load_script():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("eval_gst", ROOT / "scripts" / "eval_gst.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_golden_file_shape() -> None:
    items = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    unanswerable = [i for i in items if i.get("unanswerable")]
    answerable = [i for i in items if not i.get("unanswerable")]
    assert len(unanswerable) >= 5 and len(answerable) >= 5
    assert all(i["expected_sources"] for i in answerable)
    assert all(not i["expected_sources"] for i in unanswerable)


def test_sample_corpus_ingests_with_page_numbers_and_eval_runs(
    conn, gateway: Gateway, provider: FakeProvider
) -> None:  # type: ignore[no-untyped-def]
    results = asyncio.run(ingest.ingest_corpus(conn, gateway, ROOT / "evals" / "corpus_sample"))
    assert [r.status for r in results] == ["ingested", "ingested"]
    titles = {r["title"] for r in conn.execute("SELECT title FROM documents")}
    golden_sources = {
        s
        for line in GOLDEN.read_text().splitlines()
        if line.strip()
        for s in json.loads(line)["expected_sources"]
    }
    assert golden_sources <= titles
    pages = {r["page"] for r in conn.execute("SELECT page FROM chunks")}
    assert pages == {1, 2, 3}

    script = load_script()
    golden = script.load_golden(GOLDEN)
    for item in golden:
        if item.get("unanswerable"):
            provider.push("NOT_SUPPORTED")
        else:
            provider.push(
                "According to the notes [1] [2] [3] [4] [5].", '{"score": 1, "reason": "matches"}'
            )
    report = asyncio.run(script.run_eval(conn, gateway, FakeReranker(), golden))
    assert "Unanswerable questions refused: 6/6 (100%)" in report
    assert "Answer correctness (judged by the text model): 7/7" in report
    assert "Citation recall (answerable)" in report
    assert (
        conn.execute("SELECT COUNT(*) FROM qa_logs").fetchone()[0] == 0
    )  # evals leave no business logs
