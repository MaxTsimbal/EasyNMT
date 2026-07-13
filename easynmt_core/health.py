"""Hosting health endpoints.

The liveness endpoint must never depend on SQLite, Google OAuth, OpenAI, or a
mounted volume. Railway only needs proof that the web process can answer HTTP.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> tuple[object, int]:
    return jsonify(status="ok", service="EasyNMT"), 200


@health_bp.get("/ready")
def ready() -> tuple[object, int]:
    """Lightweight readiness endpoint kept separate from external services."""
    return jsonify(status="ready"), 200
