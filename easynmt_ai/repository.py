from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

from .schemas import AttachmentRef


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AIRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        # SQLite on Railway may receive overlapping requests from Gunicorn threads.
        # A generous timeout + WAL prevents short writes from turning into
        # "database is locked" errors.
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def user_exists(self, user_id: int) -> bool:
        conn = self.connect()
        try:
            return conn.execute("SELECT 1 FROM users WHERE id = ?", (int(user_id),)).fetchone() is not None
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        conn = self.connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'Нова розмова',
                subject TEXT,
                lesson_id INTEGER,
                response_mode TEXT NOT NULL DEFAULT 'explain',
                pinned INTEGER NOT NULL DEFAULT 0,
                last_response_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (id, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_messages (
                id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                provider_mode TEXT NOT NULL DEFAULT 'demo',
                response_id TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                PRIMARY KEY (id, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_attachments (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                conversation_id TEXT,
                message_id TEXT,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'image',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_message_feedback (
                user_id INTEGER NOT NULL,
                message_id TEXT NOT NULL,
                rating TEXT NOT NULL CHECK(rating IN ('up', 'down')),
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, message_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
                ON ai_messages(user_id, conversation_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_ai_conversations_updated
                ON ai_conversations(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_attachments_user
                ON ai_attachments(user_id, created_at DESC);
            """
        )
        conn.commit()

        # Early pre-beta builds used a globally unique message ID. Migrate it to
        # a user-scoped key so a client-supplied ID can never collide across accounts.
        pk_columns = [
            row["name"]
            for row in sorted(conn.execute("PRAGMA table_info(ai_messages)").fetchall(), key=lambda item: item["pk"])
            if row["pk"]
        ]
        if pk_columns == ["id"]:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript(
                """
                BEGIN;
                ALTER TABLE ai_messages RENAME TO ai_messages_legacy;
                CREATE TABLE ai_messages (
                    id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    provider_mode TEXT NOT NULL DEFAULT 'demo',
                    response_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (id, user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                INSERT INTO ai_messages
                    (id, conversation_id, user_id, role, content, provider_mode, response_id, metadata_json, created_at)
                SELECT id, conversation_id, user_id, role, content, provider_mode, response_id, metadata_json, created_at
                FROM ai_messages_legacy;
                DROP TABLE ai_messages_legacy;
                COMMIT;
                """
            )
            conn.execute("PRAGMA foreign_keys = ON")

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
                ON ai_messages(user_id, conversation_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_ai_conversations_updated
                ON ai_conversations(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_attachments_user
                ON ai_attachments(user_id, created_at DESC);
            """
        )
        conn.commit()
        conn.close()

    def upsert_conversation(
        self,
        *,
        user_id: int,
        conversation_id: str,
        title: str,
        subject: str,
        lesson_id: Optional[int],
        response_mode: str,
    ) -> None:
        now = utc_now()
        conn = self.connect()
        try:
            if conn.execute("SELECT 1 FROM users WHERE id = ?", (int(user_id),)).fetchone() is None:
                raise ValueError(f"AI conversation user does not exist: {user_id}")
            conn.execute(
                """
                INSERT INTO ai_conversations
                    (id, user_id, title, subject, lesson_id, response_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, user_id) DO UPDATE SET
                    title = CASE WHEN ai_conversations.title IN ('', 'Нова розмова') THEN excluded.title ELSE ai_conversations.title END,
                    subject = excluded.subject,
                    lesson_id = excluded.lesson_id,
                    response_mode = excluded.response_mode,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, user_id, title or "Нова розмова", subject, lesson_id, response_mode, now, now),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def add_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        user_id: int,
        role: str,
        content: str,
        provider_mode: str = "demo",
        response_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        now = utc_now()
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO ai_messages
                    (id, conversation_id, user_id, role, content, provider_mode, response_id, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, user_id) DO UPDATE SET
                    content = excluded.content,
                    provider_mode = excluded.provider_mode,
                    response_id = excluded.response_id,
                    metadata_json = excluded.metadata_json
                """,
                (
                    message_id, conversation_id, user_id, role, content, provider_mode,
                    response_id, json.dumps(metadata or {}, ensure_ascii=False), now,
                ),
            )
            if role == "assistant" and response_id:
                conn.execute(
                    "UPDATE ai_conversations SET updated_at = ?, last_response_id = ? WHERE id = ? AND user_id = ?",
                    (now, response_id, conversation_id, user_id),
                )
            else:
                conn.execute(
                    "UPDATE ai_conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (now, conversation_id, user_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_attachment(self, *, user_id: int, attachment: AttachmentRef, conversation_id: str = "") -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO ai_attachments
                (id, user_id, conversation_id, original_name, stored_path, mime_type, size_bytes, kind, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (
                attachment.id,
                user_id,
                conversation_id or None,
                attachment.original_name,
                attachment.stored_path,
                attachment.mime_type,
                attachment.size_bytes,
                attachment.kind,
                utc_now(),
            ),
        )
        conn.commit()
        conn.close()

    def get_attachments(self, *, user_id: int, attachment_ids: Iterable[str]) -> list[AttachmentRef]:
        ids = list(dict.fromkeys(str(item) for item in attachment_ids if item))[:3]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        conn = self.connect()
        rows = conn.execute(
            f"SELECT * FROM ai_attachments WHERE user_id = ? AND id IN ({placeholders})",
            [user_id, *ids],
        ).fetchall()
        conn.close()
        indexed = {
            row["id"]: AttachmentRef(
                id=row["id"],
                original_name=row["original_name"],
                mime_type=row["mime_type"],
                size_bytes=int(row["size_bytes"]),
                stored_path=row["stored_path"],
                kind=row["kind"],
            )
            for row in rows
        }
        return [indexed[item] for item in ids if item in indexed]

    def attach_to_message(self, *, user_id: int, attachment_ids: Iterable[str], message_id: str, conversation_id: str) -> None:
        ids = list(dict.fromkeys(str(item) for item in attachment_ids if item))[:3]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        conn = self.connect()
        conn.execute(
            f"""
            UPDATE ai_attachments
            SET message_id = ?, conversation_id = ?
            WHERE user_id = ? AND id IN ({placeholders})
            """,
            [message_id, conversation_id, user_id, *ids],
        )
        conn.commit()
        conn.close()

    def set_feedback(self, *, user_id: int, message_id: str, rating: str) -> bool:
        if rating not in {"up", "down"}:
            raise ValueError("Unsupported feedback value")
        conn = self.connect()
        owned = conn.execute(
            "SELECT 1 FROM ai_messages WHERE id = ? AND user_id = ? AND role = 'assistant'",
            (message_id, user_id),
        ).fetchone()
        if not owned:
            conn.close()
            return False
        conn.execute(
            """
            INSERT INTO ai_message_feedback(user_id, message_id, rating, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, message_id) DO UPDATE SET rating = excluded.rating, created_at = excluded.created_at
            """,
            (user_id, message_id, rating, utc_now()),
        )
        conn.commit()
        conn.close()
        return True

    def get_history(self, *, user_id: int, conversation_id: str, limit: int = 12) -> list[dict[str, str]]:
        conn = self.connect()
        rows = conn.execute(
            """
            SELECT role, content
            FROM ai_messages
            WHERE user_id = ? AND conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, conversation_id, max(1, min(40, int(limit)))),
        ).fetchall()
        conn.close()
        return [
            {"role": row["role"], "text": row["content"]}
            for row in reversed(rows)
            if row["role"] in {"user", "assistant"} and str(row["content"] or "").strip()
        ]

    def list_conversations(self, *, user_id: int, limit: int = 30) -> list[dict]:
        conn = self.connect()
        conversations = conn.execute(
            """
            SELECT id, title, subject, lesson_id, response_mode, pinned, created_at, updated_at
            FROM ai_conversations WHERE user_id = ?
            ORDER BY pinned DESC, updated_at DESC LIMIT ?
            """,
            (user_id, max(1, min(100, int(limit)))),
        ).fetchall()
        result: list[dict] = []
        for conversation in conversations:
            messages = conn.execute(
                """
                SELECT id, role, content, provider_mode, created_at
                FROM ai_messages WHERE user_id = ? AND conversation_id = ?
                ORDER BY created_at ASC LIMIT 80
                """,
                (user_id, conversation["id"]),
            ).fetchall()
            result.append({
                "id": conversation["id"],
                "title": conversation["title"],
                "subject": conversation["subject"],
                "lesson_id": conversation["lesson_id"],
                "response_mode": conversation["response_mode"],
                "pinned": bool(conversation["pinned"]),
                "created_at": conversation["created_at"],
                "updated_at": conversation["updated_at"],
                "messages": [
                    {
                        "id": row["id"],
                        "role": row["role"],
                        "text": row["content"],
                        "mode": row["provider_mode"],
                        "createdAt": row["created_at"],
                    }
                    for row in messages
                ],
            })
        conn.close()
        return result

    def update_conversation(self, *, user_id: int, conversation_id: str, title: Optional[str] = None, pinned: Optional[bool] = None) -> bool:
        fields: list[str] = []
        values: list[object] = []
        if title is not None:
            fields.append("title = ?")
            values.append(str(title).strip()[:90] or "Нова розмова")
        if pinned is not None:
            fields.append("pinned = ?")
            values.append(1 if pinned else 0)
        if not fields:
            return False
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.extend([conversation_id, user_id])
        conn = self.connect()
        cursor = conn.execute(
            f"UPDATE ai_conversations SET {', '.join(fields)} WHERE id = ? AND user_id = ?",
            values,
        )
        conn.commit()
        changed = cursor.rowcount > 0
        conn.close()
        return changed

    def delete_conversation(self, *, user_id: int, conversation_id: str) -> bool:
        conn = self.connect()
        attachment_rows = conn.execute(
            "SELECT stored_path FROM ai_attachments WHERE user_id = ? AND conversation_id = ?",
            (user_id, conversation_id),
        ).fetchall()
        conn.execute("DELETE FROM ai_messages WHERE user_id = ? AND conversation_id = ?", (user_id, conversation_id))
        conn.execute("DELETE FROM ai_attachments WHERE user_id = ? AND conversation_id = ?", (user_id, conversation_id))
        cursor = conn.execute("DELETE FROM ai_conversations WHERE user_id = ? AND id = ?", (user_id, conversation_id))
        conn.commit()
        changed = cursor.rowcount > 0
        conn.close()
        for row in attachment_rows:
            try:
                os.remove(row["stored_path"])
            except OSError:
                pass
        return changed

    def count_attachments_since(self, *, user_id: int, since: str) -> int:
        conn = self.connect()
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM ai_attachments WHERE user_id = ? AND created_at >= ?",
            (user_id, since),
        ).fetchone()
        conn.close()
        return int(row["total"] or 0) if row else 0
