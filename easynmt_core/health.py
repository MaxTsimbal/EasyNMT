"""Hosting health and v1.0 Beta readiness endpoints.

`/health` is a dependency-free liveness probe for Railway. `/ready` performs
local deterministic checks for SQLite, storage, backups, and provider
configuration. It never calls Google or OpenAI over the network.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from .beta_readiness import BetaReadinessService, RELEASE_CHANNEL, RELEASE_VERSION

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health() -> tuple[object, int]:
    return (
        jsonify(
            status="ok",
            service="EasyNMT",
            release=current_app.config.get("APP_VERSION", RELEASE_VERSION),
            channel=current_app.config.get("RELEASE_CHANNEL", RELEASE_CHANNEL),
        ),
        200,
    )


@health_bp.get("/ready")
def ready() -> tuple[object, int]:
    """Return 200 only when all release-blocking local checks pass."""

    service = current_app.extensions.get("easynmt_beta_readiness")
    if not isinstance(service, BetaReadinessService):
        service = BetaReadinessService(current_app.config)
    report = service.run()
    include_checks = bool(current_app.testing or current_app.debug) and request.args.get("details") == "1"
    return jsonify(report.as_dict(include_checks=include_checks)), 200 if report.ready else 503
