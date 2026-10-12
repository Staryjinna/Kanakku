PY := backend/.venv/bin

.PHONY: setup dev build run test lint ingest eval-bills eval-gst backup seed

setup:
	python3 -m venv backend/.venv
	$(PY)/pip install -e "backend[dev]"
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

ingest eval-bills eval-gst backup seed:
	@echo "'$@' is not implemented yet (planned for a later phase)"; exit 1
