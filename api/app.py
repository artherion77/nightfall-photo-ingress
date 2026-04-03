"""FastAPI application factory for nightfall-photo-ingress web control plane."""

from contextlib import asynccontextmanager
import sqlite3
from typing import Generator

from fastapi import FastAPI, Depends
from nightfall_photo_ingress.config import load_config, AppConfig
from nightfall_photo_ingress.domain.registry import Registry

from api.auth import set_app_config_for_auth
from api.routers import health, staging, audit_log, config, blocklist
from api.rapiddoc import router as rapiddoc_router

# Global state
_app_config: AppConfig | None = None
_registry_conn: sqlite3.Connection | None = None


def get_app_config() -> AppConfig:
    """Get the application configuration."""
    if _app_config is None:
        raise RuntimeError("App config not initialized")
    return _app_config


def get_registry_connection() -> sqlite3.Connection:
    """Get the registry database connection."""
    if _registry_conn is None:
        raise RuntimeError("Registry connection not initialized")
    return _registry_conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    
    global _app_config, _registry_conn
    
    # Startup
    try:
        _app_config = load_config("/etc/nightfall/photo-ingress.conf")
        set_app_config_for_auth(_app_config)
        
        # Initialize registry and get connection
        registry = Registry(_app_config.core.registry_path)
        registry.initialize()
        
        _registry_conn = sqlite3.connect(
            _app_config.core.registry_path,
            check_same_thread=False
        )
        _registry_conn.row_factory = sqlite3.Row
        
    except Exception as e:
        print(f"Failed to initialize app: {e}")
        raise
    
    yield
    
    # Shutdown
    if _registry_conn:
        _registry_conn.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="nightfall-photo-ingress API",
        description="Web control plane for photo ingress pipeline",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Include routers
    app.include_router(health.router)
    app.include_router(staging.router)
    app.include_router(audit_log.router)
    app.include_router(config.router)
    app.include_router(blocklist.router)
    app.include_router(rapiddoc_router)
    
    return app


app = create_app()

