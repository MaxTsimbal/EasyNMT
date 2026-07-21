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
    OPENAI_TUTOR_FAST_MODEL = os.environ.get("OPENAI_TUTOR_FAST_MODEL", OPENAI_MODEL)
    OPENAI_TUTOR_MODEL = os.environ.get("OPENAI_TUTOR_MODEL", OPENAI_MODEL)
    OPENAI_TUTOR_REASONING_MODEL = os.environ.get(
        "OPENAI_TUTOR_REASONING_MODEL", OPENAI_TUTOR_MODEL
    )
    OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", OPENAI_TUTOR_MODEL)
    OPENAI_GRADING_MODEL = os.environ.get("OPENAI_GRADING_MODEL", OPENAI_TUTOR_REASONING_MODEL)
    OPENAI_MAX_OUTPUT_TOKENS = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "900"))
    OPENAI_CURRICULUM_MAX_OUTPUT_TOKENS = int(
        os.environ.get("OPENAI_CURRICULUM_MAX_OUTPUT_TOKENS", "5000")
    )
    OPENAI_LESSON_MAX_OUTPUT_TOKENS = int(
        os.environ.get("OPENAI_LESSON_MAX_OUTPUT_TOKENS", "6500")
    )
    OPENAI_WRITTEN_GRADING_MAX_OUTPUT_TOKENS = int(
        os.environ.get("OPENAI_WRITTEN_GRADING_MAX_OUTPUT_TOKENS", "2600")
    )
    OPENAI_WRITTEN_GRADING_ENABLED = (
        os.environ.get("OPENAI_WRITTEN_GRADING_ENABLED", "1") == "1"
    )
    OPENAI_FINAL_SOLUTION_MODEL = os.environ.get(
        "OPENAI_FINAL_SOLUTION_MODEL", OPENAI_VISION_MODEL
    )
    OPENAI_FINAL_SOLUTION_MAX_OUTPUT_TOKENS = int(
        os.environ.get("OPENAI_FINAL_SOLUTION_MAX_OUTPUT_TOKENS", "1800")
    )
    OPENAI_FINAL_SOLUTION_ENABLED = (
        os.environ.get("OPENAI_FINAL_SOLUTION_ENABLED", "1") == "1"
    )
    QUIZ_SOLUTION_PHOTO_MAX_BYTES = int(
        os.environ.get("QUIZ_SOLUTION_PHOTO_MAX_BYTES", str(6 * 1024 * 1024))
    )
    QUIZ_SOLUTION_PHOTO_MAX_DIMENSION = int(
        os.environ.get("QUIZ_SOLUTION_PHOTO_MAX_DIMENSION", "2400")
    )
    ALLOW_DETERMINISTIC_LESSON_FALLBACK = (
        os.environ.get(
            "EASYNMT_ALLOW_DETERMINISTIC_LESSON_FALLBACK",
            "0" if os.environ.get("RAILWAY_ENVIRONMENT") else "1",
        )
        == "1"
    )
    ALLOW_DEVELOPMENT_LESSON_FALLBACK = ALLOW_DETERMINISTIC_LESSON_FALLBACK
    OPENAI_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "45"))
    OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
    OPENAI_STORE_RESPONSES = os.environ.get("OPENAI_STORE_RESPONSES", "0") == "1"
    OPENAI_DAILY_LIMIT = int(os.environ.get("OPENAI_DAILY_LIMIT", "40"))
    OPENAI_MAX_QUESTION_CHARS = int(os.environ.get("OPENAI_MAX_QUESTION_CHARS", "1500"))
    AI_MAX_ATTACHMENTS = int(os.environ.get("AI_MAX_ATTACHMENTS", "3"))
    AI_DAILY_UPLOAD_LIMIT = int(os.environ.get("AI_DAILY_UPLOAD_LIMIT", "20"))
    AI_MAX_ATTACHMENT_BYTES = int(os.environ.get("AI_MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024)))

    APP_VERSION = "1.0.0-beta.2"
    RELEASE_CHANNEL = "beta"
    AUTO_BACKUP_ENABLED = (
        os.environ.get("EASYNMT_AUTO_BACKUP", "1") == "1"
    )
    BACKUP_INTERVAL_HOURS = float(
        os.environ.get("EASYNMT_BACKUP_INTERVAL_HOURS", "24")
    )
    BACKUP_MAX_AGE_HOURS = float(
        os.environ.get("EASYNMT_BACKUP_MAX_AGE_HOURS", "30")
    )
    BACKUP_RETENTION_COUNT = int(
        os.environ.get("EASYNMT_BACKUP_RETENTION", "7")
    )
    BETA_MIN_FREE_BYTES = int(
        os.environ.get("EASYNMT_BETA_MIN_FREE_BYTES", str(20 * 1024 * 1024))
    )
    BETA_REQUIRE_PERSISTENT_VOLUME = (
        os.environ.get(
            "EASYNMT_BETA_REQUIRE_PERSISTENT_VOLUME",
            "1" if os.environ.get("RAILWAY_ENVIRONMENT") else "0",
        )
        == "1"
    )
    BETA_REQUIRE_OPENAI = (
        os.environ.get(
            "EASYNMT_BETA_REQUIRE_OPENAI",
            "1" if os.environ.get("RAILWAY_ENVIRONMENT") else "0",
        )
        == "1"
    )
    BETA_REQUIRE_BACKUP = (
        os.environ.get(
            "EASYNMT_BETA_REQUIRE_BACKUP",
            "1" if os.environ.get("RAILWAY_ENVIRONMENT") else "0",
        )
        == "1"
    )
    BETA_REQUIRE_GOOGLE_OAUTH = (
        os.environ.get("EASYNMT_BETA_REQUIRE_GOOGLE_OAUTH", "0") == "1"
    )
    WEB_CONCURRENCY = int(os.environ.get("WEB_CONCURRENCY", "1"))
    GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
