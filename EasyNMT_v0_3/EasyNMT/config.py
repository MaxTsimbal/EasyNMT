import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "EasyNMT_2026_SECRET"

    DEBUG = True