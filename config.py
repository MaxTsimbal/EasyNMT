import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "EasyNMT_2026_SECRET_CHANGE_ME"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_DAILY_LIMIT = int(os.environ.get("OPENAI_DAILY_LIMIT", "40"))
    OPENAI_MAX_QUESTION_CHARS = int(os.environ.get("OPENAI_MAX_QUESTION_CHARS", "1500"))
