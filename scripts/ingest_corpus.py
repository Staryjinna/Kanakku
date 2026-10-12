"""Load PDFs from data/corpus/ (or --dir) into the GST search index. Needs Ollama (embeddings).

Usage: python scripts/ingest_corpus.py [--dir PATH] [--reset]
Idempotent: files already ingested (same content hash) are skipped.
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db  # noqa: E402
from app.config import Settings  # noqa: E402
from app.gst_qa import ingest  # noqa: E402
from app.llm.gateway import Gateway  # noqa: E402
from app.llm.providers.ollama import OllamaProvider  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(ROOT / "data" / "corpus"))
    parser.add_argument("--reset", action="store_true", help="drop the index first")
    args = parser.parse_args()
    folder = Path(args.dir)
    if not folder.is_dir() or not list(folder.glob("*.pdf")):
        print(f"No PDFs found in {folder}. Put GST documents there first.", file=sys.stderr)
        return 1
    settings = Settings()
    provider = OllamaProvider(settings.ollama_url, settings.llm_timeout_s)
    if not await provider.ping():
        print(f"Ollama is not reachable at {settings.ollama_url}", file=sys.stderr)
        return 1
    conn = db.connect(settings.db_path)
    db.migrate(conn)
    if args.reset:
        ingest.reset_index(conn)
    try:
        results = await ingest.ingest_corpus(conn, Gateway(provider, conn, settings), folder)
    except ingest.IngestError as exc:
        print(exc, file=sys.stderr)
        return 1
    for r in results:
        print(f"{r.status:10} {r.path}  chunks={r.chunks}")
    return 1 if any(r.status.startswith("failed") for r in results) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
