"""Shared SQLite connection helpers for the gradual modular migration."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(database_path: str) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection
