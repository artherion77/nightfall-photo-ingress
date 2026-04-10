"""FastAPI application factory for nightfall-photo-ingress web control plane."""

from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, Response

from nightfall_photo_ingress.config import AppConfig, load_config
from nightfall_photo_ingress.domain.registry import Registry

from api.rapiddoc import router as rapiddoc_router
from api.routers import audit_log, blocklist, config, health, staging, thumbnails, triage


class SPAStaticFiles(StaticFiles):
    """Static file mount with SPA fallback to 200.html or index.html."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            response = await super().get_response(path, scope)
            if response.status_code != 404:
                return response
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise

        root = Path(self.directory)
        fallback_200 = root / "200.html"
        if fallback_200.exists():
            return FileResponse(str(fallback_200))

        fallback_index = root / "index.html"
        if fallback_index.exists():
            return FileResponse(str(fallback_index))

        return await super().get_response(path, scope)


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

        app.state.config_path = config_path

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

    @app.middleware("http")
    async def cors_and_security_middleware(request, call_next):
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }

        origin = request.headers.get("origin")
        app_cfg = getattr(request.app.state, "app_config", None)
        allowed_origins = (
            app_cfg.web.cors_allowed_origins
            if app_cfg is not None
            else ("http://localhost:8000",)
        )

        if (
            request.method == "OPTIONS"
            and origin
            and request.headers.get("access-control-request-method")
        ):
            response = Response(status_code=200)
            if origin in allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Idempotency-Key"
                response.headers["Vary"] = "Origin"
            for key, value in security_headers.items():
                response.headers[key] = value
            return response

        response = await call_next(request)
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"

        for key, value in security_headers.items():
            response.headers[key] = value

        return response

    app.include_router(health.router)
    app.include_router(staging.router)
    app.include_router(audit_log.router)
    app.include_router(config.router)
    app.include_router(blocklist.router)
    app.include_router(triage.router)
    app.include_router(thumbnails.router)
    app.include_router(rapiddoc_router)

    web_build = Path(__file__).resolve().parent.parent / "webui" / "build"
    app.mount(
        "/",
        SPAStaticFiles(directory=str(web_build), html=True, check_dir=False),
        name="spa",
    )

    return app


app = create_app()

