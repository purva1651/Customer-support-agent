from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.dependencies import AppServices, create_services
from app.api.routes_admin import router as admin_router
from app.api.routes_chat import router as chat_router


def create_app(
    services: AppServices | None = None,
    config_directory: Path = Path("config"),
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        owns_services = services is None
        application.state.services = services or await create_services(config_directory)
        try:
            yield
        finally:
            if owns_services:
                await application.state.services.close()

    application = FastAPI(
        title="Ticket Support Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(chat_router)
    application.include_router(admin_router)
    return application


app = create_app()
