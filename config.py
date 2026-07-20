import os
import secrets
from datetime import timedelta


def _secret_key() -> str:
    configured = os.environ.get("SECRET_KEY", "").strip()
    production = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    known_placeholders = {
        "replace-with-a-long-random-secret",
        "EasyNMT_2026_SECRET_CHANGE_ME",
    }
    if production and (
        len(configured) < 32
        or configured in known_placeholders
    ):
        raise RuntimeError("SECRET_KEY must be at least 32 characters and random in production")
    return configured or secrets.token_urlsafe(48)


class Config:
    SECRET_KEY = _secret_key()
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = bool(os.environ.get("RAILWAY_ENVIRONMENT")) or os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    SESSION_COOKIE_NAME = "easynmt_session"
    SESSION_REFRESH_EACH_REQUEST = True
    PREFERRED_URL_SCHEME = "https" if os.environ.get("RAILWAY_ENVIRONMENT") else "http"
    TRUST_PROXY_HEADERS = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", OPENAI_MODEL)
    OPENAI_MAX_OUTPUT_TOKENS = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "900"))
    OPENAI_CURRICULUM_MAX_OUTPUT_TOKENS = int(
        os.environ.get("OPENAI_CURRICULUM_MAX_OUTPUT_TOKENS", "5000")
    )
    OPENAI_LESSON_MAX_OUTPUT_TOKENS = int(
        os.environ.get("OPENAI_LESSON_MAX_OUTPUT_TOKENS", "6500")
    )
    ALLOW_DEVELOPMENT_LESSON_FALLBACK = (
        not bool(os.environ.get("RAILWAY_ENVIRONMENT"))
        and os.environ.get("EASYNMT_ALLOW_DEVELOPMENT_LESSON_FALLBACK", "1") == "1"
    )
    OPENAI_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "45"))
    OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
    OPENAI_STORE_RESPONSES = os.environ.get("OPENAI_STORE_RESPONSES", "0") == "1"
    OPENAI_DAILY_LIMIT = int(os.environ.get("OPENAI_DAILY_LIMIT", "40"))
    OPENAI_MAX_QUESTION_CHARS = int(os.environ.get("OPENAI_MAX_QUESTION_CHARS", "1500"))
    AI_MAX_ATTACHMENTS = int(os.environ.get("AI_MAX_ATTACHMENTS", "3"))
    AI_DAILY_UPLOAD_LIMIT = int(os.environ.get("AI_DAILY_UPLOAD_LIMIT", "20"))
    AI_MAX_ATTACHMENT_BYTES = int(os.environ.get("AI_MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024)))
    GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
