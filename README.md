# Kanakku AI

Back-office assistant for small Indian businesses: bill capture with GST validation, a GST Q&A
assistant with citations, a ledger/dashboard, and payment follow-up drafts. Everything runs on your
own machine: one SQLite file and a local Ollama model server. No third-party services at runtime.

> Status: **Phase 4 (follow-ups)**. Bill capture, cited GST Q&A, ledger, dashboard, exports and payment reminders.
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

## GST assistant

Answers come **only** from documents you load; nothing is answered from the model's own memory.

```sh
cp ~/Downloads/*.pdf data/corpus/     # official CBIC / GST Council PDFs: Acts, Rules, circulars, FAQs
make ingest                           # chunk, embed (Ollama) and index; safe to re-run
make ingest ARGS=--reset              # rebuild after changing EMBED_MODEL
```

Search is hybrid: FTS5 keyword search plus sqlite-vec similarity, fused with reciprocal rank fusion,
then re-ranked with a local cross-encoder (`RERANK_MODEL`, downloaded once by sentence-transformers;
installed by `make setup`). `GET /api/health` shows `reranker: off` if it is missing, which lowers
answer quality. If the excerpts don't support an answer, or the model doesn't cite them, the app
refuses and suggests asking a CA.

`make eval-gst` scores citation recall, answer correctness (the text model as judge) and refusal of
unanswerable questions, and writes `evals/results/gst_<date>.md`. To try it without official PDFs:

```sh
python scripts/make_sample_corpus.py                      # tiny paraphrased notes, NOT official
make ingest ARGS="--dir evals/corpus_sample --reset"
make eval-gst
```

Replace `evals/gst_golden.jsonl` with questions drawn from your real corpus for a meaningful result.

## Ledger, exports and your data

- **Ledger:** confirmed bills, filterable by month, category, vendor and status, with search.
- **Dashboard:** this month's purchases, input GST (CGST/SGST/IGST), top categories, bills awaiting review and overdue receivables.
- **Export:** pick a month on the Ledger page, then download CSV or Excel (GST columns included).
- **Account page:** business details, download all your data (zip with `data.json` and your bill files), and delete the account with all its data and uploads.

## Payment follow-ups

Add customers (with a phone and/or email) and sales invoices; anything open past its due date shows
as overdue. For an overdue invoice Kanakku drafts a reminder in your business language (English or
Tamil, set on the Account page):

- Tone follows days overdue: gentle (under 15), firm (15 to 45), final (over 45).
- One model call, checked against the facts (customer name, invoice number, amount still due, no
  invented amounts, dates, fees or threats), and at most one repair call. If the draft still fails,
  a fixed template is used instead.
- You edit and approve the message, then open it in **your own** WhatsApp (`wa.me` link) or email
  (`mailto:` link) and send it. Nothing is ever sent by the server. Mark it sent afterwards.

Scenarios for tone, amount, name and invented details live in `evals/followup_scenarios.jsonl` and
run in `make test`. The Tamil templates and prompts should be reviewed by a native speaker before
real use. `make seed` creates a demo account (`demo@kanakku.local`) with sample data.

## Backup and restore

```sh
make backup                                   # data/backups/kanakku-<timestamp>.db, newest 14 kept
cp -a data/uploads/ /your/backup/uploads/     # bill files are not inside the database backup
```

Backups use SQLite's online backup, so they are safe while the app runs. To restore:

```sh
# 1. stop the app
make backup ARGS="--restore data/backups/kanakku-<timestamp>.db"
#    (your current database is kept next to it as kanakku.db.before-restore)
# 2. start the app again
```

Run `make backup` daily with cron, e.g. `0 2 * * * cd /path/to/kanakku && make backup`.

## Limitations

An assistant, not a tax filing service. Always verify with your CA before acting.
