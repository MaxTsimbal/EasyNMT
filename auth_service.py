"""Надійний Google OAuth для EasyNMT без Authlib.

Сервіс використовує стандартний OAuth 2.0 Authorization Code Flow:
1. створює захищений state;
2. перенаправляє користувача на Google;
3. обмінює code на access token;
4. отримує підтверджені дані профілю через Google UserInfo.

Секрети читаються тільки зі змінних середовища та ніколи не логуються.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


class GoogleAuthError(RuntimeError):
    """Безпечна помилка Google OAuth без витоку секретів."""


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    name: str
    picture: str
    email_verified: bool


class GoogleAuthService:
    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(self) -> None:
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

    def is_ready(self) -> bool:
        """Готовність залежить лише від наявності двох Railway Variables."""
        return bool(self.client_id and self.client_secret)

    def create_state(self) -> str:
        return secrets.token_urlsafe(32)

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        if not self.is_ready():
            raise GoogleAuthError("Google OAuth credentials are missing")

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "include_granted_scopes": "true",
            "prompt": "select_account",
        }
        return f"{self.AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> GoogleProfile:
        if not self.is_ready():
            raise GoogleAuthError("Google OAuth credentials are missing")
        if not code:
            raise GoogleAuthError("Google did not return an authorization code")

        try:
            token_response = requests.post(
                self.TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.exception("Google token request failed")
            raise GoogleAuthError("Не вдалося з’єднатися з Google") from exc

        if token_response.status_code != 200:
            # Логуємо лише тип помилки, без client_secret, code або token.
            payload: dict[str, Any] = {}
            try:
                payload = token_response.json()
            except ValueError:
                pass
            logger.error(
                "Google token endpoint returned status=%s error=%s",
                token_response.status_code,
                payload.get("error", "unknown"),
            )
            raise GoogleAuthError("Google не підтвердив вхід")

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise GoogleAuthError("Google не повернув токен доступу")

        try:
            user_response = requests.get(
                self.USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.exception("Google userinfo request failed")
            raise GoogleAuthError("Не вдалося отримати дані Google-акаунта") from exc

        if user_response.status_code != 200:
            logger.error("Google userinfo endpoint returned status=%s", user_response.status_code)
            raise GoogleAuthError("Google не передав дані акаунта")

        info = user_response.json()
        sub = str(info.get("sub") or "").strip()
        email = str(info.get("email") or "").strip().lower()
        name = str(info.get("name") or "").strip()
        picture = str(info.get("picture") or "").strip()
        email_verified_raw = info.get("email_verified", False)
        email_verified = email_verified_raw is True or str(email_verified_raw).lower() == "true"

        if not sub or not email:
            raise GoogleAuthError("Google не передав email або ідентифікатор акаунта")

        return GoogleProfile(
            sub=sub,
            email=email,
            name=name or email.split("@")[0],
            picture=picture,
            email_verified=email_verified,
        )

    def safe_status(self) -> dict[str, object]:
        return {
            "client_id_present": bool(self.client_id),
            "client_secret_present": bool(self.client_secret),
            "google_client_ready": self.is_ready(),
            "implementation": "oauth2_requests",
        }
