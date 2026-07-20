"""SQLite persistence and delivery-token primitives for production lessons."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from easynmt_ai.lessons import Lesson

from .errors import (
    CurriculumLessonDeliveryInvalid,
    CurriculumLessonNotFound,
    CurriculumLessonOwnershipError,
    CurriculumLessonPersistenceError,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class CurriculumLessonRepository:
    """Own additive lesson schema and owner-scoped lesson persistence."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def ensure_schema(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS curriculum_lessons (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    generation_source TEXT NOT NULL CHECK(generation_source = 'openai'),
                    schema_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_identifier TEXT NOT NULL,
                    provider_response_id TEXT,
                    input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
                    output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
                    total_tokens INTEGER CHECK(total_tokens IS NULL OR total_tokens >= 0),
                    generated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, curriculum_id, curriculum_unit_id, request_fingerprint),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_lesson_deliveries (
                    id TEXT PRIMARY KEY,
                    completion_token_hash TEXT NOT NULL UNIQUE,
                    evidence_id TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    lesson_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    served_at TEXT NOT NULL,
                    completed_at TEXT,
                    evidence_verified_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE,
                    FOREIGN KEY (lesson_id) REFERENCES curriculum_lessons(id) ON DELETE CASCADE,
                    CHECK(
                        (completed_at IS NULL AND evidence_verified_at IS NULL) OR
                        (completed_at IS NOT NULL AND evidence_verified_at IS NOT NULL)
                    )
                );

                CREATE TABLE IF NOT EXISTS curriculum_lesson_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL CHECK(event_type IN (
                        'lesson_generated', 'lesson_cache_hit', 'lesson_delivered',
                        'lesson_generation_failed', 'lesson_completion_accepted',
                        'lesson_completion_rejected'
                    )),
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    lesson_id TEXT,
                    reason TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE,
                    FOREIGN KEY (lesson_id) REFERENCES curriculum_lessons(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_curriculum_lessons_lookup
                    ON curriculum_lessons(
                        user_id, curriculum_id, curriculum_unit_id, request_fingerprint
                    );
                CREATE INDEX IF NOT EXISTS idx_curriculum_lessons_topic
                    ON curriculum_lessons(user_id, topic_id, generated_at);
                CREATE INDEX IF NOT EXISTS idx_curriculum_lesson_delivery_lookup
                    ON curriculum_lesson_deliveries(
                        user_id, curriculum_id, curriculum_unit_id, completed_at
                    );
                CREATE INDEX IF NOT EXISTS idx_curriculum_lesson_events_lookup
                    ON curriculum_lesson_events(user_id, curriculum_id, created_at);
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _lesson_from_row(row: sqlite3.Row) -> Lesson:
        raw = row["content_json"]
        try:
            payload = json.loads(raw)
            lesson = Lesson.from_dict(payload)
        except Exception as exc:
            raise CurriculumLessonPersistenceError(
                "Stored lesson content failed validation."
            ) from exc
        if content_hash(payload) != row["content_hash"]:
            raise CurriculumLessonPersistenceError("Stored lesson content hash does not match.")
        if lesson.id != row["id"] or lesson.curriculum_id != row["curriculum_id"]:
            raise CurriculumLessonPersistenceError("Stored lesson ownership metadata is invalid.")
        return lesson

    def cached_lesson(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_id: str,
        curriculum_unit_id: str,
        request_fingerprint: str,
    ) -> Lesson | None:
        row = connection.execute(
            """
            SELECT * FROM curriculum_lessons
            WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?
              AND request_fingerprint = ?
            """,
            (
                int(user_id),
                curriculum_id,
                curriculum_unit_id,
                request_fingerprint,
            ),
        ).fetchone()
        return None if row is None else self._lesson_from_row(row)

    def save_lesson(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        lesson: Lesson,
    ) -> Lesson:
        payload = lesson.to_dict()
        serialized = canonical_json(payload)
        digest = content_hash(payload)
        metadata = lesson.generation_metadata
        connection.execute(
            """
            INSERT OR IGNORE INTO curriculum_lessons (
                id, user_id, curriculum_id, curriculum_unit_id, topic_id,
                request_fingerprint, content_hash, content_json, generation_source,
                schema_version, prompt_version, model_identifier,
                provider_response_id, input_tokens, output_tokens, total_tokens,
                generated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lesson.id,
                int(user_id),
                lesson.curriculum_id,
                lesson.curriculum_unit_id,
                lesson.topic_id,
                metadata.request_fingerprint,
                digest,
                serialized,
                metadata.source,
                metadata.schema_version,
                metadata.prompt_version,
                metadata.model_identifier,
                metadata.provider_response_id,
                metadata.input_tokens,
                metadata.output_tokens,
                metadata.total_tokens,
                metadata.generated_at,
                utc_now(),
            ),
        )
        stored = self.cached_lesson(
            connection,
            user_id=user_id,
            curriculum_id=lesson.curriculum_id,
            curriculum_unit_id=lesson.curriculum_unit_id,
            request_fingerprint=metadata.request_fingerprint,
        )
        if stored is None:
            raise CurriculumLessonPersistenceError("Lesson could not be stored.")
        if stored.to_dict() != lesson.to_dict():
            raise CurriculumLessonPersistenceError(
                "A different immutable lesson already owns this generation identity."
            )
        return stored

    def create_delivery(
        self,
        connection: sqlite3.Connection,
        *,
        delivery_id: str,
        completion_token_hash: str,
        evidence_id: str,
        user_id: int,
        lesson: Lesson,
    ) -> None:
        lesson_digest = content_hash(lesson.to_dict())
        row = connection.execute(
            "SELECT content_hash FROM curriculum_lessons WHERE id = ? AND user_id = ?",
            (lesson.id, int(user_id)),
        ).fetchone()
        if row is None or row["content_hash"] != lesson_digest:
            raise CurriculumLessonPersistenceError(
                "A delivery cannot reference unknown or changed lesson content."
            )
        connection.execute(
            """
            INSERT INTO curriculum_lesson_deliveries (
                id, completion_token_hash, evidence_id, user_id, curriculum_id,
                curriculum_unit_id, lesson_id, content_hash, served_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery_id,
                completion_token_hash,
                evidence_id,
                int(user_id),
                lesson.curriculum_id,
                lesson.curriculum_unit_id,
                lesson.id,
                lesson_digest,
                utc_now(),
            ),
        )

    def delivery_row(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_unit_id: str,
        completion_token_hash: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT d.*, l.request_fingerprint, l.content_json,
                   l.content_hash AS lesson_content_hash,
                   l.curriculum_id AS lesson_curriculum_id,
                   l.curriculum_unit_id AS lesson_curriculum_unit_id,
                   c.status AS curriculum_status, c.subject
            FROM curriculum_lesson_deliveries d
            JOIN curriculum_lessons l ON l.id = d.lesson_id
            JOIN ai_curricula c ON c.id = d.curriculum_id
            WHERE d.completion_token_hash = ?
            """,
            (completion_token_hash,),
        ).fetchone()
        if row is None:
            raise CurriculumLessonDeliveryInvalid("Lesson delivery token is invalid.")
        if int(row["user_id"]) != int(user_id):
            raise CurriculumLessonOwnershipError(
                "Lesson delivery does not belong to this user."
            )
        if row["curriculum_unit_id"] != curriculum_unit_id:
            raise CurriculumLessonDeliveryInvalid(
                "Lesson delivery token does not match this unit."
            )
        return row

    @staticmethod
    def complete_delivery(
        connection: sqlite3.Connection,
        *,
        delivery_id: str,
        completed_at: str,
    ) -> bool:
        cursor = connection.execute(
            """
            UPDATE curriculum_lesson_deliveries
            SET completed_at = ?, evidence_verified_at = ?
            WHERE id = ? AND completed_at IS NULL
            """,
            (completed_at, completed_at, delivery_id),
        )
        return cursor.rowcount == 1

    @staticmethod
    def insert_event(
        connection: sqlite3.Connection,
        *,
        event_key: str,
        event_type: str,
        user_id: int,
        curriculum_id: str,
        curriculum_unit_id: str,
        reason: str,
        lesson_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> bool:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO curriculum_lesson_events (
                event_key, event_type, user_id, curriculum_id,
                curriculum_unit_id, lesson_id, reason, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                event_type,
                int(user_id),
                curriculum_id,
                curriculum_unit_id,
                lesson_id,
                reason,
                canonical_json(metadata or {}),
                created_at or utc_now(),
            ),
        )
        return cursor.rowcount == 1

    def get_lesson(self, *, user_id: int, lesson_id: str) -> Lesson:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM curriculum_lessons WHERE id = ?",
                (lesson_id,),
            ).fetchone()
            if row is None:
                raise CurriculumLessonNotFound("Lesson not found.")
            if int(row["user_id"]) != int(user_id):
                raise CurriculumLessonOwnershipError("Lesson does not belong to this user.")
            return self._lesson_from_row(row)
        finally:
            connection.close()

    def list_events(
        self,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM curriculum_lesson_events
                WHERE user_id = ? AND curriculum_id = ? ORDER BY id
                """,
                (int(user_id), curriculum_id),
            ).fetchall()
            return [
                {**dict(row), "metadata": json.loads(row["metadata_json"])}
                for row in rows
            ]
        finally:
            connection.close()
