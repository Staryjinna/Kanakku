PY := backend/.venv/bin

.PHONY: setup dev build run test lint ingest eval-bills eval-gst backup seed

setup:
	python3 -m venv backend/.venv
	$(PY)/pip install -e "backend[dev,rerank]"
	cd frontend && npm ci
	@test -f .env || cp .env.example .env

dev:
	cd backend && ../$(PY)/uvicorn app.main:create_app --factory --reload --port 8000 & \
	cd frontend && npm run dev

build:
	cd frontend && npm run build

run: build
	cd backend && ../$(PY)/uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000

test:
	cd backend && ../$(PY)/pytest -q

lint:
	cd backend && ../$(PY)/ruff check . && ../$(PY)/ruff format --check . && ../$(PY)/mypy app
	cd frontend && npm run typecheck

eval-bills:
	$(PY)/python scripts/eval_bills.py

ingest:
	$(PY)/python scripts/ingest_corpus.py $(ARGS)

eval-gst:
	$(PY)/python scripts/eval_gst.py

backup:
	$(PY)/python scripts/backup.py $(ARGS)

seed:
	$(PY)/python scripts/seed_demo.py $(ARGS)
