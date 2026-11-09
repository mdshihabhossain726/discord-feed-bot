"""FastAPI application entry point (Phase 1: foundation + health check only)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config.logging import configure_logging
from app.config.settings import get_settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("starting", extra={"env": settings.app_env})
    yield
    log.info("shutdown complete")


def create_app() -> FastAPI:
    """Application factory (keeps tests independent of global state)."""
    app = FastAPI(title="RedditBridge", version="0.1.0", lifespan=lifespan)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        # Phase 1: liveness only. DB/Discord/Reddit/worker checks are added in later phases.
        return {"status": "ok"}

    return app


app = create_app()
