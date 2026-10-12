# Kanakku AI

Back-office assistant for small Indian businesses: bill capture with GST validation, a GST Q&A
assistant with citations, a ledger/dashboard, and payment follow-up drafts. Everything runs on your
own machine: one SQLite file and a local Ollama model server. No third-party services at runtime.

> Status: **Phase 1 (bill capture)**. Upload a bill, review the extracted fields with GST checks, confirm.
> Features land phase by phase; see `CLAUDE.md`.

## Architecture

- `backend/` FastAPI app, SQLite (WAL) with plain SQL migrations, asyncio job worker.
- `backend/app/llm/gateway.py` is the only way to call AI (Ollama; `FakeProvider` in tests).
- `frontend/` React + Vite + Tailwind, built to `frontend/dist` and served by FastAPI.

## Setup

```sh
make setup            # venv, deps, frontend deps, copies .env.example to .env
# edit .env: set JWT_SECRET
ollama pull qwen2.5:7b && ollama pull qwen2.5vl:7b && ollama pull nomic-embed-text
```

## Run

```sh
make dev              # backend (reload) on :8000 + Vite on :5173
make run              # production-style: build frontend, serve everything on :8000
make test lint
docker compose up     # app + ollama
```

`GET /api/health` reports database status and whether Ollama is reachable.

## Bill capture

Upload a JPG/PNG/WEBP/PDF (<= 10 MB) on the Bills page. A background job reads it with the local vision
(or, for text PDFs, text) model, runs GST checks (GSTIN format and checksum, line amounts, totals,
CGST/SGST vs IGST, GST slabs, date), and puts it in "Needs review". Nothing reaches the ledger until
you confirm. Scanned PDFs are supported when the page is a single embedded scan.

`make eval-bills` runs extraction on `evals/bills/` (needs Ollama) and writes `evals/results/bills_<date>.md`.
The bundled samples are synthetic (`scripts/make_sample_bills.py`); add real, redacted bills with a
matching `.json` file for a meaningful accuracy number.

## Limitations

An assistant, not a tax filing service. Always verify with your CA before acting.
