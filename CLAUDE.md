# CLAUDE.md — Kanakku AI

This file is the source of truth for building Kanakku AI. Read it fully at the start of every session.
Build ONE phase per session. Always show a plan and wait for approval before writing code.

---

## 1. Product

Kanakku AI is a back-office assistant for small Indian businesses (shops, clinics, traders, freelancers).

- **Bill capture:** owner uploads a photo/PDF of a purchase bill → AI extracts fields → GST validation → owner reviews → saved to ledger.
- **GST assistant:** answers GST questions ONLY from official documents we load, with citations; refuses when unsupported.
- **Ledger & dashboard:** monthly totals, input GST summary, CSV/Excel export.
- **Payment follow-ups:** tracks overdue sales invoices; AI drafts reminders (English/Tamil); owner approves and sends via their own WhatsApp (`wa.me` link) or email (`mailto:` link).

Positioning: an assistant, not a tax filing service. Every GST answer ends with "Please verify with your CA before acting."

---

## 2. Hard rules (never break these)

1. **No third-party services at runtime.** No hosted databases, hosted LLM APIs, auth providers, analytics, error trackers, email/SMS/WhatsApp APIs, CDNs, or cloud storage. Open-source libraries installed via pip/npm are fine.
2. **Storage = one SQLite file** (`data/kanakku.db`, WAL mode) + local folder `data/uploads/`. Tests use `:memory:` SQLite and a temp folder.
3. **All AI goes through `app/llm/gateway.py`.** No module imports an AI client directly. The only provider is Ollama at `OLLAMA_URL` (default `http://localhost:11434`). Tests use `FakeProvider`.
4. **Multi-tenant isolation:** every business-owned table has `business_id`; every query filters by the current user's `business_id`. Write a test per module proving user A cannot read user B's data.
5. **AI never acts alone:** extracted bills are drafts until the owner confirms; reminder messages are drafts until the owner sends them.
6. **No secrets in git.** Config from `.env`; commit `.env.example` only. `data/` is gitignored.
7. **No PII in logs:** redact PAN, GSTIN, phone numbers, emails, and bank account numbers before writing to `llm_calls` or application logs.
8. Do not add a dependency outside the allowed list (section 3) without asking.
9. Keep it simple: one backend process, one frontend build, no microservices, no Redis, no Celery.

---

## 3. Stack and allowed dependencies

**Backend (Python 3.12):** fastapi, uvicorn, pydantic, pydantic-settings, httpx, argon2-cffi, pyjwt, python-multipart, sqlite-vec, pypdf, pillow, openpyxl, sentence-transformers (local re-ranker only), numpy.
Dev: pytest, pytest-asyncio, ruff, mypy.

**Frontend:** React 18 + Vite + TypeScript + Tailwind CSS + react-router + recharts. Built into `frontend/dist` and served by FastAPI as static files. No external fonts or CDNs.

**AI (via Ollama, names set in `.env`):**
- `LLM_TEXT_MODEL` (e.g. `qwen2.5:7b`)
- `LLM_VISION_MODEL` (e.g. `qwen2.5vl:7b`)
- `EMBED_MODEL` (e.g. `nomic-embed-text`)
- `RERANK_MODEL` (e.g. `BAAI/bge-reranker-base`, loaded locally with sentence-transformers; downloaded once)

---

## 4. Repository layout

```
kanakku/
├── CLAUDE.md
├── README.md
├── .env.example
├── Makefile
├── Dockerfile
├── docker-compose.yml          # app + ollama
├── .github/workflows/ci.yml    # lint + tests (uses FakeProvider, no Ollama)
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py             # FastAPI app, routers, static frontend, startup (migrations, worker)
│   │   ├── config.py           # pydantic-settings
│   │   ├── db.py               # SQLite connection, WAL, sqlite-vec loading, migration runner
│   │   ├── migrations/         # 0001_init.sql, 0002_bills.sql, ...
│   │   ├── auth/               # router.py, service.py, deps.py (current_user, current_business)
│   │   ├── llm/                # gateway.py, providers/ollama.py, providers/fake.py, redact.py, cache.py
│   │   ├── jobs/               # queue.py (SQLite jobs table), worker.py (asyncio loop)
│   │   ├── bills/              # router, service, extract.py, validate.py, schemas.py
│   │   ├── ledger/             # router, service, export.py
│   │   ├── gst_qa/             # ingest.py, chunk.py, search.py, rerank.py, answer.py, router.py
│   │   ├── followups/          # router, agent.py, templates.py
│   │   └── observability/      # router (metrics endpoints for dashboard)
│   └── tests/
├── frontend/
│   └── src/ (pages: Login, Signup, Dashboard, Bills, BillReview, Ledger, Ask, Followups, Admin)
├── evals/
│   ├── bills/                  # sample images + expected JSON (same filename, .json)
│   ├── gst_golden.jsonl        # {"question", "expected_answer", "expected_sources": [...]}
│   └── followup_scenarios.jsonl
├── scripts/
│   ├── ingest_corpus.py        # loads data/corpus/*.pdf into the search index
│   ├── eval_bills.py
│   ├── eval_gst.py
│   ├── backup.py               # SQLite online backup to BACKUP_DIR
│   └── seed_demo.py            # demo business with sample data
└── data/                       # gitignored: kanakku.db, uploads/, corpus/, backups/
```

Makefile targets: `setup`, `dev` (backend reload + Vite), `build`, `run`, `test`, `lint`, `ingest`, `eval-bills`, `eval-gst`, `backup`, `seed`.

---

## 5. Data model (SQLite)

Use plain SQL migrations applied in order and tracked in `schema_migrations`. Money stored as integer paise. Timestamps ISO-8601 UTC text.

- `users(id, email UNIQUE, password_hash, name, created_at)`
- `businesses(id, owner_user_id, name, gstin NULL, state_code, language DEFAULT 'en', created_at)`
- `parties(id, business_id, kind 'vendor'|'customer', name, gstin NULL, phone NULL, email NULL)`
- `bills(id, business_id, party_id NULL, status 'processing'|'needs_review'|'confirmed'|'failed', file_path, bill_no, bill_date, taxable_paise, cgst_paise, sgst_paise, igst_paise, total_paise, category, extraction_json, confidence_json, validation_json, created_at, confirmed_at)`
- `bill_items(id, bill_id, description, hsn NULL, qty, rate_paise, gst_rate, amount_paise)`
- `sales_invoices(id, business_id, party_id, invoice_no, invoice_date, due_date, total_paise, paid_paise, status 'open'|'paid')`
- `followups(id, business_id, invoice_id, channel 'whatsapp'|'email', draft_text, status 'draft'|'approved'|'sent'|'rejected', created_at, sent_at)`
- `documents(id, title, source_url NULL, file_path, ingested_at)` — GST corpus is shared across businesses
- `chunks(id, document_id, page, ordinal, text)` + `chunks_fts` (FTS5 on text) + `chunks_vec` (sqlite-vec vec0, dimension from EMBED_MODEL)
- `qa_logs(id, business_id, question, answer, cited_chunk_ids, refused, latency_ms, created_at)`
- `jobs(id, kind, payload_json, status 'queued'|'running'|'done'|'failed', attempts, error, created_at, updated_at)`
- `llm_cache(key PRIMARY KEY, response_json, created_at)`
- `llm_calls(id, business_id NULL, purpose, model, prompt_tokens, completion_tokens, latency_ms, cache_hit, error NULL, redacted_prompt_preview, created_at)`

---

## 6. Module specifications

### 6.1 Auth
- `POST /api/auth/signup` (email, password ≥ 10 chars, name, business name, state) → creates user + business.
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.
- argon2 hashing; JWT (HS256, `JWT_SECRET` from env, 7-day expiry) in an httpOnly, SameSite=Lax cookie; `Secure` when `ENV=prod`.
- Login rate limit: 5 failed attempts per email per 15 minutes (tracked in SQLite).
- Signup includes a consent checkbox for the privacy policy; store consent timestamp.

### 6.2 LLM gateway
- `gateway.chat(messages, model=None, json_schema=None, images=None, purpose, business_id)` and `gateway.embed(texts)`.
- Provider interface with `OllamaProvider` (httpx to Ollama `/api/chat` and `/api/embed`) and `FakeProvider` (deterministic, for tests).
- Structured output: pass JSON schema to Ollama `format`; validate with Pydantic; one repair retry on invalid JSON.
- Timeouts (`LLM_TIMEOUT_S`, default 180), 2 retries with backoff on connection errors.
- Cache: key = sha256(model + messages + schema); only for deterministic calls (temperature 0); not for images by default.
- Log every call to `llm_calls` with redacted prompt preview (first 300 chars after `redact.py`).
- `redact.py`: regexes for PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), GSTIN, Indian mobile numbers, emails, long digit runs (account numbers). Unit-tested.

### 6.3 Jobs
- `enqueue(kind, payload)` inserts into `jobs`. Worker = asyncio task started on app startup, polls every 1s, runs one job at a time (local model is the bottleneck), max 3 attempts, marks failed with error.
- On startup, reset `running` jobs to `queued`.
- `GET /api/jobs/{id}` for UI polling.

### 6.4 Bills (Phase 1)
- `POST /api/bills` (multipart image/PDF, ≤ 10 MB, types: jpg, png, webp, pdf) → save to `data/uploads/{business_id}/{uuid}.{ext}`, create bill `processing`, enqueue `extract_bill`.
- PDF: extract text with pypdf; if text is meaningful, use text model; otherwise render first page to image (Pillow) and use vision model.
- Extraction schema (Pydantic): vendor name, vendor GSTIN, bill number, bill date, line items (description, HSN, qty, rate, GST rate, amount), taxable value, CGST, SGST, IGST, total, plus per-field confidence (high/medium/low).
- Validation (`validate.py`, pure functions, fully unit-tested):
  - GSTIN format `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$` and checksum
  - line item amounts ≈ qty × rate (tolerance ₹1)
  - taxable + taxes ≈ total (tolerance ₹1)
  - intra-state (vendor state = business state) → CGST = SGST and IGST = 0; inter-state → IGST only
  - GST rate in {0, 0.25, 3, 5, 12, 18, 28}
  - date not in the future, not older than 2 years
- Result: status `needs_review` with `validation_json` listing issues; low-confidence fields flagged.
- Review screen: original image left, editable fields right, issues highlighted; "Confirm" re-validates and sets `confirmed`; auto-create/match vendor in `parties`.
- Category suggestion (text model, from a fixed list: stock purchase, rent, utilities, salaries, transport, office supplies, professional fees, repairs, other).
- `scripts/eval_bills.py`: runs extraction on `evals/bills/*`, compares to expected JSON, prints per-field accuracy and average latency, writes `evals/results/bills_<date>.md`.

### 6.5 GST assistant (Phase 2)
- `make ingest`: read `data/corpus/*.pdf`, extract text per page, chunk (~800 tokens, 100 overlap, keep page numbers), embed in batches, insert into `chunks`, `chunks_fts`, `chunks_vec`. Idempotent by file hash.
- Search: top 20 from FTS5 (BM25) + top 20 from sqlite-vec → reciprocal rank fusion (k=60) → re-rank top 20 with local cross-encoder → keep top 5.
- Answer: text model with strict system prompt — answer only from provided chunks, cite as [1], [2] mapping to (document title, page); if chunks do not support an answer, reply with a refusal and suggest asking a CA. Set `refused=true`.
- Response: answer text, citations (doc title, page, snippet), refused flag. Streaming via server-sent events.
- UI: chat page; citations clickable → panel showing the chunk text and document/page.
- `scripts/eval_gst.py`: for each golden question, checks whether expected sources appear in citations (citation recall), and uses the text model as judge for answer correctness vs expected answer (score 0/1 with reason). Also includes ≥ 5 unanswerable questions that must be refused. Writes `evals/results/gst_<date>.md`.

### 6.6 Ledger & dashboard (Phase 3)
- Ledger list with filters (month, category, vendor, status), search, pagination.
- Dashboard: this month's purchases, input GST (CGST/SGST/IGST), top categories (recharts), bills needing review, overdue receivables.
- Export: CSV and Excel (openpyxl) per month, GST columns included.
- Onboarding flow after signup (business details, language, first bill upload).
- `scripts/backup.py` using SQLite online backup API; keep last 14; document restore in README; Makefile target.
- Mobile-first layout check at 375px width.
- Privacy page, account data export, and account deletion (deletes business data and uploads).

### 6.7 Payment follow-ups (Phase 4)
- CRUD for customers and sales invoices; mark paid.
- Overdue = open and past due date.
- Agent (simple, explicit steps — not an open-ended loop): for a selected invoice, gather context (customer, amount, days overdue, previous follow-ups) → choose tone (gentle < 15 days, firm 15–45, final > 45) → draft message in business language (English or Tamil) → return draft. Max 1 LLM call + 1 repair.
- UI: list of overdue invoices, "Draft reminder" → editable draft → Approve → shows `https://wa.me/<phone>?text=<urlencoded>` and `mailto:` buttons → owner clicks → mark `sent`.
- Never send automatically. Scenario tests in `evals/followup_scenarios.jsonl` (tone, amount, name correct, no invented facts).

### 6.8 Hardening (Phase 5)
- Admin/metrics page: LLM calls per day, p50/p95 latency, cache hit rate, errors, calls by purpose.
- Rate limit per user on AI endpoints (e.g. 60 calls/hour).
- Security pass: upload type sniffing (not just extension), path traversal checks, CSRF protection for cookie auth (double-submit token), security headers, dependency audit (`pip-audit`, `npm audit`).
- Verify no PII in `llm_calls` via test.

---

## 7. Conventions

- Python: type hints everywhere, ruff + mypy clean, small functions, services hold logic, routers stay thin.
- API under `/api/...`, JSON, Pydantic request/response models, errors as `{"detail": ...}`.
- Frontend: TypeScript strict, one API client module, loading/empty/error states on every page, works at 375px.
- Tests: every module has tests; LLM calls use `FakeProvider`; DB is `:memory:`. CI must pass without Ollama.
- Commits: one logical change each, conventional commit messages.
- README: what it is, screenshot/GIF, architecture, setup (Ollama models), run, evals results, limitations.

---

## 8. Phases and exit checks

| Phase | Scope | Exit check |
|---|---|---|
| 0 Foundation | Layout, config, DB + migrations, auth, gateway (Ollama + Fake), jobs skeleton, health, React login/signup/empty dashboard, Makefile, Docker, CI | `make lint test` pass; signup → login → dashboard works; `/api/health` shows DB ok and Ollama reachable; a gateway call is logged in `llm_calls` |
| 1 Bill capture | Section 6.4 | Validation tests pass; upload → review → confirm works end to end; `make eval-bills` produces a report |
| 2 GST assistant | Section 6.5 | `make ingest` works on sample PDFs; cited answers in UI; unanswerable questions refused; `make eval-gst` produces a report |
| 3 Ledger & pilot readiness | Section 6.6 | Exports open in Excel; backup + restore tested; onboarding works on a 375px screen |
| 4 Follow-ups | Section 6.7 | Nothing sends without approval; scenario tests pass |
| 5 Hardening | Section 6.8 | Metrics page live; PII test passes; security checklist done |

**Current status:** Phase 3 complete. Next: Phase 4. (Update this line after each phase.)

---

## 9. How to work in each session

1. Read this file. Confirm which phase we are on.
2. Present a short plan (files, schema changes, open questions). Wait for approval.
3. Implement in small steps; run tests as you go.
4. Run `make lint` and `make test` (and the phase's eval target) until green.
5. Report: what was built, how to run it, exit check results, open issues. Do not start the next phase.
