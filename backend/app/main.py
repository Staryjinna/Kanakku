import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db, health
from app.account.router import router as account_router
from app.auth.router import router as auth_router
from app.bills import service as bills_service
from app.bills.router import router as bills_router
from app.config import Settings, get_settings
from app.followups.router import router as followups_router
from app.gst_qa.rerank import Reranker, get_reranker
from app.gst_qa.router import router as gst_router
from app.jobs.router import router as jobs_router
from app.jobs.worker import Worker
from app.ledger.router import router as ledger_router
from app.llm.gateway import Gateway
from app.llm.providers.base import Provider
from app.llm.providers.ollama import OllamaProvider
from app.observability.router import router as metrics_router
from app.security import CSRFMiddleware, SecurityHeadersMiddleware, install_log_redaction

logging.basicConfig(level=logging.INFO)
install_log_redaction()


def create_app(
    settings: Settings | None = None,
    provider: Provider | None = None,
    reranker: Reranker | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = db.connect(settings.db_path)
        db.migrate(conn)
        Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
        prov = provider or OllamaProvider(settings.ollama_url, settings.llm_timeout_s)
        worker = Worker(conn)
        app.state.settings = settings
        app.state.db = conn
        app.state.provider = prov
        app.state.gateway = Gateway(prov, conn, settings)
        app.state.worker = worker
        app.state.reranker = reranker or get_reranker(settings)
        bills_service.register_handlers(worker, conn, app.state.gateway, settings)
        if settings.worker_enabled:
            worker.start()
        yield
        await worker.stop()
        conn.close()

    app = FastAPI(
        title="Kanakku AI",
        lifespan=lifespan,
        docs_url=None,  # Swagger UI loads scripts from a CDN, which this app never does
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )
    app.add_middleware(CSRFMiddleware, enabled=settings.csrf_enabled)
    app.add_middleware(SecurityHeadersMiddleware, prod=settings.is_prod)  # outermost
    app.include_router(health.router)
    app.include_router(auth_router)
    app.include_router(jobs_router)
    app.include_router(bills_router)
    app.include_router(gst_router)
    app.include_router(ledger_router)
    app.include_router(account_router)
    app.include_router(followups_router)
    app.include_router(metrics_router)
    _mount_frontend(app, Path(settings.frontend_dist))
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)
