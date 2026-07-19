import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "EasyNMT_2026_SECRET_CHANGE_ME"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1" if os.environ.get("RAILWAY_ENVIRONMENT") else "0") == "1"
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", OPENAI_MODEL)
    OPENAI_MAX_OUTPUT_TOKENS = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "900"))
    OPENAI_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "45"))
    OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1"))
    OPENAI_STORE_RESPONSES = os.environ.get("OPENAI_STORE_RESPONSES", "0") == "1"
    OPENAI_DAILY_LIMIT = int(os.environ.get("OPENAI_DAILY_LIMIT", "40"))
    OPENAI_MAX_QUESTION_CHARS = int(os.environ.get("OPENAI_MAX_QUESTION_CHARS", "1500"))
    AI_MAX_ATTACHMENTS = int(os.environ.get("AI_MAX_ATTACHMENTS", "3"))
    AI_DAILY_UPLOAD_LIMIT = int(os.environ.get("AI_DAILY_UPLOAD_LIMIT", "20"))
    AI_MAX_ATTACHMENT_BYTES = int(os.environ.get("AI_MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024)))
    GOOGLE_SITE_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
