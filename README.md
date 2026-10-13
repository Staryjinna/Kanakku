# Kanakku AI

Back-office assistant for small Indian businesses: bill capture with GST validation, a GST Q&A
assistant with citations, a ledger/dashboard, and payment follow-up drafts. Everything runs on your
own machine: one SQLite file and a local Ollama model server. No third-party services at runtime.

> Status: **Phase 5 (hardening) complete**. Bill capture, cited GST Q&A, ledger, dashboard, exports, payment
> reminders, AI usage metrics and a security pass.
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

## Low-memory machines (8 GB RAM, no GPU)

The default models (7B) need roughly 6 GB each. On an 8 GB laptop use the low-memory profile at the bottom
of `.env.example` (3B models, a small re-ranker, a longer timeout), and close the browser tabs you don't need:

```sh
ollama pull qwen2.5:3b && ollama pull qwen2.5vl:3b && ollama pull nomic-embed-text
make setup-lite        # skips the large cross-encoder install; or `make setup` and keep the small re-ranker
export OLLAMA_MAX_LOADED_MODELS=1   # before starting Ollama: keep only one model in memory at a time
```

Expect a bill to take one to a few minutes and answers to stream slowly. Smaller models misread more:
review every bill, and run `make eval-bills` to see how accurate your setup really is. Text PDFs are
read faster and more accurately than photos.

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

## Operations and security

- **AI usage page** (`/admin`): calls per day, p50/p95 latency, cache hit rate, errors, calls by purpose, job
  queue. Visible only to emails listed in `ADMIN_EMAILS` (comma-separated); nobody is admin by default.
- **Rate limit:** 60 AI requests per user per hour (`AI_RATE_LIMIT_PER_HOUR`) across bill reads, GST
  questions and reminder drafts; over the limit the API answers 429 with `Retry-After`.
- **Production:** set `ENV=prod` (secure cookies, HSTS, no API schema) and a random `JWT_SECRET`
  (>= 32 characters; the app refuses to start otherwise). Serve it behind HTTPS.

Security checklist (each item has tests):

- [x] Uploads: type from magic bytes (never the file name), must actually decode, 10 MB / 40 megapixel /
  100 page limits, encrypted PDFs refused, stored under a server-chosen name in the business's own folder
- [x] Path traversal: files are only served from the caller's own upload folder; data export checks the same
- [x] CSRF: double-submit token (`kanakku_csrf` cookie echoed in `X-CSRF-Token`) plus an `Origin` check on
  every state-changing API call made with the session cookie
- [x] Cookies: session is `HttpOnly`, `SameSite=Lax`, `Secure` in prod
- [x] Headers: CSP (self only, no third-party origins), `nosniff`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, HSTS in prod, `Cache-Control: no-store` on API responses
- [x] No PII in `llm_calls`, job/bill error text or application logs: PAN, GSTIN, phone, email and long numbers
  are redacted (`tests/test_pii.py` runs every AI feature with PII-laden input)
- [x] Tenant isolation: every module has a test that user A cannot read or change user B's data
- [x] Login rate limit (5 failures / 15 min per email), argon2 password hashing
- [x] Dependency audit: `make audit` (`pip-audit` and `npm audit --omit=dev`) is clean and runs in CI.
  `npm audit` (all deps) still reports advisories in Tailwind 3's build-time dependencies (glob and CSS
  parsing at build time on our own files); they never ship to users. Upgrading to Tailwind 4 clears them.

## Limitations

An assistant, not a tax filing service. Always verify with your CA before acting.
