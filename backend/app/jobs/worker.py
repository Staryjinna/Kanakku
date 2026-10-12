import asyncio
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any

from app.jobs import queue

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]
FailureHandler = Callable[[dict[str, Any], str], Awaitable[None]]


class Worker:
    """Runs one job at a time (the local model is the bottleneck)."""

    def __init__(self, conn: sqlite3.Connection, poll_s: float = 1.0) -> None:
        self.conn = conn
        self.poll_s = poll_s
        self.handlers: dict[str, Handler] = {}
        self.failure_handlers: dict[str, FailureHandler] = {}
        self._task: asyncio.Task[None] | None = None

    def register(
        self, kind: str, handler: Handler, on_failure: FailureHandler | None = None
    ) -> None:
        """`on_failure(payload, error)` runs once the job has used all its attempts."""
        self.handlers[kind] = handler
        if on_failure:
            self.failure_handlers[kind] = on_failure

    async def run_once(self) -> bool:
        """Process one queued job. Returns False if the queue was empty."""
        job = queue.claim_next(self.conn)
        if job is None:
            return False
        handler = self.handlers.get(job["kind"])
        try:
            if handler is None:
                raise RuntimeError(f"No handler for job kind '{job['kind']}'")
            await handler(json.loads(job["payload_json"]))
        except Exception as exc:  # job failures must never kill the worker loop
            logger.warning("job %s failed: %s", job["id"], type(exc).__name__)
            error = f"{type(exc).__name__}: {exc}"
            queue.mark_failed(self.conn, job["id"], job["attempts"], error)
            give_up = self.failure_handlers.get(job["kind"])
            if give_up and job["attempts"] >= queue.MAX_ATTEMPTS:
                try:
                    await give_up(json.loads(job["payload_json"]), error)
                except Exception:
                    logger.exception("failure handler error")
        else:
            queue.mark_done(self.conn, job["id"])
        return True

    async def _loop(self) -> None:
        while True:
            try:
                if not await self.run_once():
                    await asyncio.sleep(self.poll_s)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("worker loop error")
                await asyncio.sleep(self.poll_s)

    def start(self) -> None:
        queue.reset_running(self.conn)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
