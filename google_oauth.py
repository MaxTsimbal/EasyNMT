"""Small, dependency-light Google OAuth 2.0 client for Mentory.

The module reads credentials dynamically from Railway environment variables,
uses OAuth 2.0 authorization-code flow, validates state, exchanges the code,
and fetches the verified Google profile. Secret values are never logged.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from base64 import urlsafe_b64encode
from typing import Any
from urllib.parse import urlencode

import requests
from flask import current_app, session

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _normalise_key(value: str) -> str:
    return value.strip().upper().replace("-", "_").replace(" ", "_")


def read_secret(name: str) -> str:
    """Read a variable robustly, including accidental whitespace in its key."""
    direct = os.getenv(name)
    if direct and direct.strip():
        return direct.strip()

    target = _normalise_key(name)
    for key, value in os.environ.items():
        if _normalise_key(key) == target and value and value.strip():
            return value.strip()
    return ""


def credentials_status() -> dict[str, bool]:
    client_id = read_secret("GOOGLE_CLIENT_ID")
    client_secret = read_secret("GOOGLE_CLIENT_SECRET")
    return {
        "client_id_present": bool(client_id),
        "client_secret_present": bool(client_secret),
        "google_client_ready": bool(client_id and client_secret),
    }


def build_authorization_url(callback_url: str) -> str:
    client_id = read_secret("GOOGLE_CLIENT_ID")
    client_secret = read_secret("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth credentials are missing")

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")

    session["google_oauth_state"] = state
    session["google_oauth_verifier"] = verifier
    session.modified = True

    params = {
        "client_id": client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_callback(*, code: str, state: str, callback_url: str) -> dict[str, Any]:
    expected_state = session.pop("google_oauth_state", "")
    verifier = session.pop("google_oauth_verifier", "")
    session.modified = True

    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        raise ValueError("OAuth state validation failed")
    if not code or not verifier:
        raise ValueError("OAuth callback is missing required data")

    client_id = read_secret("GOOGLE_CLIENT_ID")
    client_secret = read_secret("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Google OAuth credentials are missing")

    token_response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        },
        timeout=20,
    )
    if not token_response.ok:
        current_app.logger.error(
            "Google token exchange failed: status=%s",
            token_response.status_code,
        )
        raise RuntimeError("Google token exchange failed")

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("Google did not return an access token")

    profile_response = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    if not profile_response.ok:
        current_app.logger.error(
            "Google userinfo failed: status=%s",
            profile_response.status_code,
        )
        raise RuntimeError("Google profile request failed")

    profile = profile_response.json()
    if not isinstance(profile, dict):
        raise RuntimeError("Google returned an invalid profile")
    return profile
