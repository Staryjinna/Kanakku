"""Evaluate the GST assistant on evals/gst_golden.jsonl and write evals/results/gst_<date>.md.

Needs Ollama and an ingested corpus (`make ingest`). For the bundled sample questions, first run:
  python scripts/make_sample_corpus.py && make ingest ARGS="--dir evals/corpus_sample --reset"
"""

import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402
from app.config import Settings  # noqa: E402
from app.gst_qa import answer  # noqa: E402
from app.gst_qa.rerank import Reranker, get_reranker  # noqa: E402
from app.llm.gateway import Gateway  # noqa: E402
from app.llm.providers.base import LLMError  # noqa: E402
from app.llm.providers.ollama import OllamaProvider  # noqa: E402

JUDGE_PROMPT = (
    "You grade an answer to a GST question against a reference answer. Score 1 if the answer "
    "states the same facts as the reference (extra detail is fine, contradictions are not), "
    "otherwise 0. Reply as JSON with `score` (0 or 1) and a one-sentence `reason`."
)


class Judgement(BaseModel):
    score: Literal[0, 1]
    reason: str


async def judge(gateway: Gateway, question: str, expected: str, got: str) -> Judgement:
    prompt = f"Question: {question}\n\nReference answer: {expected}\n\nAnswer to grade: {got}"
    resp = await gateway.chat(
        [{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": prompt}],
        purpose="gst_eval_judge",
        json_schema=Judgement,
    )
    assert isinstance(resp.parsed, Judgement)
    return resp.parsed


def load_golden(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run_eval(conn, gateway: Gateway, reranker: Reranker, golden: list[dict]) -> str:  # type: ignore[no-untyped-def]
    rows: list[str] = []
    recall: list[bool] = []
    correct: list[bool] = []
    refused_ok: list[bool] = []
    for item in golden:
        q = item["question"]
        try:
            final = await answer.answer_question(conn, gateway, reranker, q, None)
        except LLMError as exc:
            rows.append(f"| {q} | ERROR: {type(exc).__name__} | | |")
            (refused_ok if item.get("unanswerable") else correct).append(False)
            continue
        if item.get("unanswerable"):
            refused_ok.append(final.refused)
            rows.append(f"| {q} | unanswerable | {'refused' if final.refused else 'ANSWERED (bad)'} | |")
            continue
        titles = {c.title for c in final.citations}
        has_sources = set(item["expected_sources"]) <= titles
        recall.append(has_sources)
        if final.refused:
            correct.append(False)
            rows.append(f"| {q} | answerable | REFUSED (bad) | sources: {'ok' if has_sources else 'missing'} |")
            continue
        verdict = await judge(gateway, q, item["expected_answer"], final.answer)
        correct.append(bool(verdict.score))
        rows.append(
            f"| {q} | answerable | {'correct' if verdict.score else 'WRONG'}: {verdict.reason} "
            f"| sources: {'ok' if has_sources else 'missing'} |"
        )

    def pct(xs: list[bool]) -> str:
        return f"{sum(xs)}/{len(xs)} ({sum(xs) / len(xs):.0%})" if xs else "n/a"

    return "\n".join(
        [
            f"# GST assistant eval - {date.today().isoformat()}",
            "",
            f"Text model: `{gateway.settings.llm_text_model}`, embeddings: `{gateway.settings.embed_model}`",
            "",
            f"- Citation recall (answerable): {pct(recall)}",
            f"- Answer correctness (judged by the text model): {pct(correct)}",
            f"- Unanswerable questions refused: {pct(refused_ok)}",
            "",
            "| Question | Type | Result | Citations |",
            "|---|---|---|---|",
            *rows,
            "",
        ]
    )


async def main() -> int:
    settings = Settings()
    provider = OllamaProvider(settings.ollama_url, settings.llm_timeout_s)
    if not await provider.ping():
        print(f"Ollama is not reachable at {settings.ollama_url}", file=sys.stderr)
        return 1
    conn = db.connect(settings.db_path)
    db.migrate(conn)
    if not conn.execute("SELECT 1 FROM chunks LIMIT 1").fetchone():
        print("No documents ingested. Run `make ingest` first.", file=sys.stderr)
        return 1
    golden = load_golden(ROOT / "evals" / "gst_golden.jsonl")
    report = await run_eval(conn, Gateway(provider, conn, settings), get_reranker(settings), golden)
    out = ROOT / "evals" / "results" / f"gst_{date.today().isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(report)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
