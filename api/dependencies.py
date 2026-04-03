"""Shared FastAPI dependency providers for app state access."""

from __future__ import annotations

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
