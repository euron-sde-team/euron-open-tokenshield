"""Application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from tokenshield import __version__
from tokenshield.alerts.router import router as alerts_router
from tokenshield.audit.router import router as audit_router
from tokenshield.auth.router import router as auth_router
from tokenshield.budgets.router import router as budgets_router
from tokenshield.cache.router import router as cache_router
from tokenshield.core.config import Settings, get_settings
from tokenshield.core.container import Container
from tokenshield.core.errors import install_error_handlers
from tokenshield.core.logs import configure_logging
from tokenshield.core.middleware import RequestContextMiddleware
from tokenshield.gateway.router import router as gateway_router
from tokenshield.gateway.tokens import warm_up
from tokenshield.keys.router import router as keys_router
from tokenshield.playground.router import router as playground_router
from tokenshield.policies.router import router as policies_router
from tokenshield.projects.router import router as projects_router
from tokenshield.providers.router import router as providers_router
from tokenshield.system.router import router as system_router
from tokenshield.teams.router import router as teams_router
from tokenshield.usage.router import router as usage_router
from tokenshield.users.router import router as users_router

DESCRIPTION = """
Self-hosted AI gateway. Point any OpenAI SDK at `/v1` with a TokenShield key; every request
is attributed, priced, checked against hard budgets and waste policies, served from cache
when safe, and recorded.

The `/api/v1` endpoints power the dashboard and are available to automation with a session
token (`POST /api/v1/auth/login`).
"""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or Container.build(settings)
        await asyncio.to_thread(warm_up)
        try:
            yield
        finally:
            if container is None:
                await app.state.container.close()

    app = FastAPI(
        title="Euron TokenShield",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    install_error_handlers(app)
    for router in (
        gateway_router,
        auth_router,
        users_router,
        teams_router,
        projects_router,
        keys_router,
        providers_router,
        budgets_router,
        policies_router,
        cache_router,
        usage_router,
        alerts_router,
        audit_router,
        playground_router,
        system_router,
    ):
        app.include_router(router)

    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "authorization",
            "content-type",
            "x-tokenshield-csrf",
            "idempotency-key",
            "x-tokenshield-user",
            "x-tokenshield-task-id",
            "x-tokenshield-cache",
            "x-tokenshield-cache-scope",
            "x-request-id",
        ],
        expose_headers=[
            "x-request-id",
            "x-tokenshield-request-id",
            "x-tokenshield-cache",
            "x-tokenshield-cost-usd",
            "x-tokenshield-estimated-cost-usd",
            "x-tokenshield-avoided-cost-usd",
            "retry-after",
        ],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)
    return app
