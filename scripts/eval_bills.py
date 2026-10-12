"""Run bill extraction on evals/bills/* and write a per-field accuracy report.

Usage: python scripts/eval_bills.py   (needs Ollama running with the models from .env)
"""

import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402
from app.bills import extract  # noqa: E402
from app.bills.evaluate import FIELDS, compare, summarize  # noqa: E402
from app.bills.service import to_paise  # noqa: E402
from app.bills.validate import BillData, ItemData, validate_bill  # noqa: E402
from app.config import Settings  # noqa: E402
from app.llm.gateway import Gateway  # noqa: E402
from app.llm.providers.base import LLMError, Provider  # noqa: E402
from app.llm.providers.ollama import OllamaProvider  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


async def run_eval(gateway: Gateway, bills_dir: Path, state_code: str = "33") -> str:
    files = sorted(p for p in bills_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    rows: list[dict[str, bool]] = []
    latencies: list[float] = []
    lines: list[str] = []
    failures = 0
    for path in files:
        expected_path = path.with_suffix(".json")
        if not expected_path.exists():
            continue
        expected = json.loads(expected_path.read_text())
        start = time.monotonic()
        try:
            got = await extract.extract_bill(gateway, path, None)
        except (LLMError, extract.ExtractionError) as exc:
            failures += 1
            lines.append(f"| {path.name} | FAILED: {type(exc).__name__} |")
            continue
        latencies.append(time.monotonic() - start)
        result = compare(got, expected)
        rows.append(result)
        bad = [f for f, ok in result.items() if not ok]
        data = BillData(
            vendor_gstin=got.vendor_gstin,
            bill_no=got.bill_no,
            bill_date=date.fromisoformat(got.bill_date) if got.bill_date else None,
            taxable_paise=to_paise(got.taxable_value),
            cgst_paise=to_paise(got.cgst),
            sgst_paise=to_paise(got.sgst),
            igst_paise=to_paise(got.igst),
            total_paise=to_paise(got.total),
            items=[
                ItemData(i.qty, to_paise(i.rate) or 0, to_paise(i.amount) or 0, i.gst_rate)
                for i in got.items
            ],
        )
        issues = [i.code for i in validate_bill(data, state_code, date.today())]
        lines.append(
            f"| {path.name} | {'all correct' if not bad else 'wrong: ' + ', '.join(bad)} "
            f"| {', '.join(issues) or '-'} |"
        )
    acc = summarize(rows)
    out = [
        f"# Bill extraction eval - {date.today().isoformat()}",
        "",
        f"Text model: `{gateway.settings.llm_text_model}`, "
        f"vision model: `{gateway.settings.llm_vision_model}`",
        f"Bills: {len(files)} found, {len(rows)} extracted, {failures} failed.",
        f"Average latency: {sum(latencies) / len(latencies):.1f}s" if latencies else "No latency.",
        "",
        "## Per-field accuracy",
        "",
        "| Field | Accuracy |",
        "|---|---|",
        *[f"| {f} | {acc[f]:.0%} |" for f in FIELDS if f in acc],
        "",
        "## Per bill",
        "",
        "| Bill | Result | Validation issues |",
        "|---|---|---|",
        *lines,
        "",
    ]
    return "\n".join(out)


async def main() -> int:
    settings = Settings()
    provider: Provider = OllamaProvider(settings.ollama_url, settings.llm_timeout_s)
    if not await provider.ping():
        print(f"Ollama is not reachable at {settings.ollama_url}", file=sys.stderr)
        return 1
    conn = db.connect(":memory:")
    db.migrate(conn)
    report = await run_eval(Gateway(provider, conn, settings), ROOT / "evals" / "bills")
    results = ROOT / "evals" / "results"
    results.mkdir(parents=True, exist_ok=True)
    out = results / f"bills_{date.today().isoformat()}.md"
    out.write_text(report)
    print(report)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
