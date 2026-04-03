"""FastAPI application factory for nightfall-photo-ingress web control plane."""

from contextlib import asynccontextmanager
import sqlite3

from fastapi import FastAPI

from nightfall_photo_ingress.config import AppConfig, load_config
from nightfall_photo_ingress.domain.registry import Registry

from api.rapiddoc import router as rapiddoc_router
from api.routers import audit_log, blocklist, config, health, staging


def create_app(
    *,
    config_path: str = "/etc/nightfall/photo-ingress.conf",
    app_config: AppConfig | None = None,
    registry_conn: sqlite3.Connection | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifespan: startup and shutdown."""

        owns_registry_conn = False

        if app_config is not None:
            app.state.app_config = app_config
        else:
            app.state.app_config = load_config(config_path)

        if registry_conn is not None:
            app.state.registry_conn = registry_conn
        else:
            registry = Registry(app.state.app_config.core.registry_path)
            registry.initialize()
            conn = sqlite3.connect(
                app.state.app_config.core.registry_path,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            app.state.registry_conn = conn
            owns_registry_conn = True

        yield

        if owns_registry_conn:
            app.state.registry_conn.close()

    app = FastAPI(
        title="nightfall-photo-ingress API",
        description="Web control plane for photo ingress pipeline",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.include_router(health.router)
    app.include_router(staging.router)
    app.include_router(audit_log.router)
    app.include_router(config.router)
    app.include_router(blocklist.router)
    app.include_router(rapiddoc_router)

    return app


app = create_app()

