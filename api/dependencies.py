"""Shared FastAPI dependency providers for app state access."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi import Request

from nightfall_photo_ingress.config import AppConfig


def get_app_config(request: Request) -> AppConfig:
    """Return AppConfig from FastAPI app state."""

    app_config = getattr(request.app.state, "app_config", None)
    if app_config is None:
        raise RuntimeError("App config not initialized")
    return app_config


def get_registry_connection(request: Request) -> sqlite3.Connection:
    """Return SQLite registry connection from FastAPI app state."""

    conn = getattr(request.app.state, "registry_conn", None)
    if conn is None:
        raise RuntimeError("Registry connection not initialized")
    return conn


def get_thumbnail_cache_path(request: Request) -> Path:
    """Return thumbnail cache root from app config."""

    app_config = get_app_config(request)
    return app_config.core.thumbnail_cache_path


def get_config_path(request: Request) -> str:
    """Return config file path from FastAPI app state."""
    return getattr(request.app.state, "config_path", "/etc/nightfall/photo-ingress.conf")
