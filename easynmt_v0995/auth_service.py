"""Authentication helpers for EasyNMT.

Keeps Google OpenID Connect configuration out of app.py and exposes only
safe readiness diagnostics. Secrets are read from environment variables and
are never logged.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from authlib.integrations.flask_client import OAuth
from flask import Flask

logger = logging.getLogger(__name__)


class GoogleAuthService:
    def __init__(self, app: Flask) -> None:
        self.app = app
        self.oauth = OAuth(app)
        self.client: Any | None = None
        self._configuration_error: str | None = None
        self.configure()

    @staticmethod
    def _read_env(name: str) -> str:
        return os.environ.get(name, "").strip()

    def configure(self) -> bool:
        if self.client is not None:
            return True

        client_id = self._read_env("GOOGLE_CLIENT_ID")
        client_secret = self._read_env("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            missing = []
            if not client_id:
                missing.append("GOOGLE_CLIENT_ID")
            if not client_secret:
                missing.append("GOOGLE_CLIENT_SECRET")
            self._configuration_error = "Missing environment variables: " + ", ".join(missing)
            logger.warning(
                "Google OAuth is not ready. client_id_present=%s client_secret_present=%s",
                bool(client_id),
                bool(client_secret),
            )
            return False

        try:
            self.client = self.oauth.register(
                name="google",
                client_id=client_id,
                client_secret=client_secret,
                server_metadata_url=(
                    "https://accounts.google.com/.well-known/openid-configuration"
                ),
                client_kwargs={"scope": "openid email profile"},
            )
        except Exception as exc:
            self._configuration_error = f"OAuth client setup failed: {type(exc).__name__}"
            logger.exception("Google OAuth client setup failed")
            self.client = None
            return False

        self._configuration_error = None
        logger.info("Google OAuth client configured")
        return True

    def is_ready(self) -> bool:
        return self.configure() and self.client is not None

    def safe_status(self) -> dict[str, object]:
        return {
            "client_id_present": bool(self._read_env("GOOGLE_CLIENT_ID")),
            "client_secret_present": bool(self._read_env("GOOGLE_CLIENT_SECRET")),
            "google_client_ready": self.is_ready(),
            "configuration_error": self._configuration_error,
        }
