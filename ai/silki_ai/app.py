"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI

from silki_ai.config import Settings, get_settings
from silki_ai.container import ApplicationContainer
from silki_ai.health import router as health_router
from silki_ai.logging import configure_logging
from silki_ai.reindex_api import router as reindex_router
from silki_ai.websocket_api import router as websocket_router


def create_app(
    *,
    settings: Settings | None = None,
    container: Any | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_container = container or ApplicationContainer(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings.log_level)
        await resolved_container.start()
        try:
            yield
        finally:
            await resolved_container.close()

    application = FastAPI(
        title="Silki AI Backend",
        version="0.1.0",
        description=(
            "Streaming speech transcription and non-authoritative semantic menu recommendation"
        ),
        lifespan=lifespan,
    )
    application.state.container = resolved_container
    application.include_router(health_router)
    application.include_router(reindex_router)
    application.include_router(websocket_router)
    return application


app = create_app()


def run() -> None:
    uvicorn.run("silki_ai.app:app", host="0.0.0.0", port=8000, proxy_headers=True)


if __name__ == "__main__":
    run()
