"""Hosting health endpoints.

The liveness endpoint must never depend on SQLite, Google OAuth, OpenAI, or a
mounted volume. Railway only needs proof that the web process can answer HTTP.
"""
from __future__ import annotations

import sqlite3

from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> tuple[object, int]:
    return jsonify(status="ok", service="EasyNMT"), 200


@health_bp.get("/ready")
def ready() -> tuple[object, int]:
    """Report ready only when the application database is reachable and initialized."""
    database_path = current_app.config.get("DATABASE_PATH")
    if not database_path:
        return jsonify(status="not_ready"), 503
    try:
        with sqlite3.connect(database_path, timeout=2.0) as connection:
            schema = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone()
            if schema is None:
                return jsonify(status="not_ready"), 503
    except sqlite3.Error:
        current_app.logger.exception("Database readiness check failed")
        return jsonify(status="not_ready"), 503
    return jsonify(status="ready"), 200
