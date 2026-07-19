"""Transactional SQLite persistence for versioned curricula."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ..models import Curriculum, CurriculumStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CurriculumStateError(ValueError):
    """Raised when a lifecycle transition is not allowed."""


class CurriculumRepository:
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
                CREATE TABLE IF NOT EXISTS ai_curricula (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    curriculum_version INTEGER NOT NULL,
                    taxonomy_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_identifier TEXT NOT NULL,
                    target_score INTEGER NOT NULL,
                    starting_level TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'draft', 'validated', 'published', 'superseded', 'rejected'
                    )),
                    creation_reason TEXT NOT NULL,
                    generation_source TEXT NOT NULL CHECK(generation_source IN ('openai', 'deterministic')),
                    context_fingerprint TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    generation_metadata_json TEXT NOT NULL,
                    validation_result_json TEXT,
                    created_at TEXT NOT NULL,
                    validated_at TEXT,
                    published_at TEXT,
                    superseded_at TEXT,
                    rejected_at TEXT,
                    UNIQUE(user_id, subject, curriculum_version),
                    UNIQUE(user_id, subject, request_fingerprint),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_curriculum_units (
                    curriculum_id TEXT NOT NULL,
                    unit_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    topic_id TEXT NOT NULL,
                    prerequisite_topic_ids_json TEXT NOT NULL,
                    prerequisite_explanation TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    estimated_duration_minutes INTEGER NOT NULL,
                    study_sessions INTEGER NOT NULL,
                    mastery_target REAL NOT NULL,
                    reason_code TEXT NOT NULL,
                    PRIMARY KEY(curriculum_id, unit_id),
                    UNIQUE(curriculum_id, position),
                    UNIQUE(curriculum_id, topic_id),
                    FOREIGN KEY (curriculum_id) REFERENCES ai_curricula(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_curriculum_checkpoints (
                    curriculum_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    after_unit_order INTEGER NOT NULL,
                    topic_ids_json TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    estimated_minutes INTEGER NOT NULL,
                    PRIMARY KEY(curriculum_id, checkpoint_id),
                    UNIQUE(curriculum_id, position),
                    FOREIGN KEY (curriculum_id) REFERENCES ai_curricula(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ai_curriculum_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    curriculum_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (curriculum_id) REFERENCES ai_curricula(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_curricula_one_published
                    ON ai_curricula(user_id, subject)
                    WHERE status = 'published';
                CREATE INDEX IF NOT EXISTS idx_ai_curricula_history
                    ON ai_curricula(user_id, subject, curriculum_version DESC);
                CREATE INDEX IF NOT EXISTS idx_ai_curriculum_events
                    ON ai_curriculum_events(user_id, curriculum_id, created_at);
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        curriculum_id: str,
        user_id: int,
        from_status: Optional[str],
        to_status: str,
        reason: str,
        metadata: Optional[Mapping[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO ai_curriculum_events
                (curriculum_id, user_id, from_status, to_status, reason, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                curriculum_id,
                int(user_id),
                from_status,
                to_status,
                reason,
                self._json(metadata or {}),
                created_at or utc_now(),
            ),
        )

    def create_draft(self, curriculum: Curriculum) -> Curriculum:
        if curriculum.status is not CurriculumStatus.DRAFT:
            raise CurriculumStateError("Only draft curricula can be created")
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute(
                "SELECT 1 FROM users WHERE id = ?", (curriculum.user_id,)
            ).fetchone() is None:
                raise ValueError("Curriculum user does not exist")
            duplicate = connection.execute(
                """
                SELECT id FROM ai_curricula
                WHERE user_id = ? AND subject = ? AND request_fingerprint = ?
                """,
                (
                    curriculum.user_id,
                    curriculum.subject,
                    curriculum.generation_metadata.request_fingerprint,
                ),
            ).fetchone()
            if duplicate:
                connection.rollback()
                existing = self.get_curriculum(curriculum.user_id, duplicate["id"])
                if existing is None:
                    raise RuntimeError("Duplicate curriculum disappeared")
                return existing

            next_version = int(connection.execute(
                """
                SELECT COALESCE(MAX(curriculum_version), 0) + 1
                FROM ai_curricula WHERE user_id = ? AND subject = ?
                """,
                (curriculum.user_id, curriculum.subject),
            ).fetchone()[0])
            stored = replace(curriculum, curriculum_version=next_version)
            metadata = stored.generation_metadata
            connection.execute(
                """
                INSERT INTO ai_curricula (
                    id, user_id, subject, curriculum_version, taxonomy_version,
                    schema_version, prompt_version, model_identifier, target_score,
                    starting_level, status, creation_reason, generation_source,
                    context_fingerprint, request_fingerprint, generation_metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.id,
                    stored.user_id,
                    stored.subject,
                    stored.curriculum_version,
                    stored.taxonomy_version,
                    stored.schema_version,
                    stored.prompt_version,
                    stored.model_identifier,
                    stored.target_score,
                    stored.starting_level,
                    stored.status.value,
                    stored.creation_reason,
                    metadata.source,
                    metadata.context_fingerprint,
                    metadata.request_fingerprint,
                    self._json(metadata.to_dict()),
                    stored.created_at,
                ),
            )
            for unit in stored.units:
                connection.execute(
                    """
                    INSERT INTO ai_curriculum_units (
                        curriculum_id, unit_id, position, topic_id,
                        prerequisite_topic_ids_json, prerequisite_explanation,
                        priority, difficulty, estimated_duration_minutes,
                        study_sessions, mastery_target, reason_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.id,
                        unit.id,
                        unit.order,
                        unit.topic_id,
                        self._json(unit.prerequisite_topic_ids),
                        unit.prerequisite_explanation,
                        unit.priority,
                        unit.difficulty,
                        unit.estimated_duration_minutes,
                        unit.study_sessions,
                        unit.mastery_target,
                        unit.reason_code,
                    ),
                )
            for position, checkpoint in enumerate(stored.review_checkpoints, 1):
                connection.execute(
                    """
                    INSERT INTO ai_curriculum_checkpoints (
                        curriculum_id, checkpoint_id, position, after_unit_order,
                        topic_ids_json, reason_code, estimated_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.id,
                        checkpoint.id,
                        position,
                        checkpoint.after_unit_order,
                        self._json(checkpoint.topic_ids),
                        checkpoint.reason_code,
                        checkpoint.estimated_minutes,
                    ),
                )
            self._insert_event(
                connection,
                curriculum_id=stored.id,
                user_id=stored.user_id,
                from_status=None,
                to_status=CurriculumStatus.DRAFT.value,
                reason=stored.creation_reason,
                metadata={"source": metadata.source},
                created_at=stored.created_at,
            )
            connection.commit()
            return stored
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _load_curriculum(self, connection: sqlite3.Connection, row: sqlite3.Row) -> Curriculum:
        unit_rows = connection.execute(
            "SELECT * FROM ai_curriculum_units WHERE curriculum_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        checkpoint_rows = connection.execute(
            "SELECT * FROM ai_curriculum_checkpoints WHERE curriculum_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        payload = {
            "id": row["id"],
            "curriculum_version": row["curriculum_version"],
            "taxonomy_version": row["taxonomy_version"],
            "user_id": row["user_id"],
            "subject": row["subject"],
            "target_score": row["target_score"],
            "starting_level": row["starting_level"],
            "status": row["status"],
            "creation_reason": row["creation_reason"],
            "units": [
                {
                    "id": unit["unit_id"],
                    "order": unit["position"],
                    "topic_id": unit["topic_id"],
                    "prerequisite_topic_ids": json.loads(unit["prerequisite_topic_ids_json"]),
                    "prerequisite_explanation": unit["prerequisite_explanation"],
                    "priority": unit["priority"],
                    "difficulty": unit["difficulty"],
                    "estimated_duration_minutes": unit["estimated_duration_minutes"],
                    "study_sessions": unit["study_sessions"],
                    "mastery_target": unit["mastery_target"],
                    "reason_code": unit["reason_code"],
                }
                for unit in unit_rows
            ],
            "review_checkpoints": [
                {
                    "id": checkpoint["checkpoint_id"],
                    "after_unit_order": checkpoint["after_unit_order"],
                    "topic_ids": json.loads(checkpoint["topic_ids_json"]),
                    "reason_code": checkpoint["reason_code"],
                    "estimated_minutes": checkpoint["estimated_minutes"],
                }
                for checkpoint in checkpoint_rows
            ],
            "generation_metadata": json.loads(row["generation_metadata_json"]),
            "prompt_version": row["prompt_version"],
            "schema_version": row["schema_version"],
            "model_identifier": row["model_identifier"],
            "created_at": row["created_at"],
        }
        return Curriculum.from_dict(payload)

    def get_curriculum(self, user_id: int, curriculum_id: str) -> Optional[Curriculum]:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM ai_curricula WHERE id = ? AND user_id = ?",
                (curriculum_id, int(user_id)),
            ).fetchone()
            return self._load_curriculum(connection, row) if row else None
        finally:
            connection.close()

    def find_by_request_fingerprint(
        self,
        user_id: int,
        subject: str,
        request_fingerprint: str,
    ) -> Optional[Curriculum]:
        connection = self.connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM ai_curricula
                WHERE user_id = ? AND subject = ? AND request_fingerprint = ?
                """,
                (int(user_id), subject, request_fingerprint),
            ).fetchone()
            return self._load_curriculum(connection, row) if row else None
        finally:
            connection.close()

    def get_active(self, user_id: int, subject: str) -> Optional[Curriculum]:
        connection = self.connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM ai_curricula
                WHERE user_id = ? AND subject = ? AND status = 'published'
                """,
                (int(user_id), subject),
            ).fetchone()
            return self._load_curriculum(connection, row) if row else None
        finally:
            connection.close()

    def get_history(self, user_id: int, subject: str) -> list[Curriculum]:
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM ai_curricula
                WHERE user_id = ? AND subject = ?
                ORDER BY curriculum_version DESC
                """,
                (int(user_id), subject),
            ).fetchall()
            return [self._load_curriculum(connection, row) for row in rows]
        finally:
            connection.close()

    def save_validation(
        self,
        *,
        user_id: int,
        curriculum_id: str,
        validation_result: Mapping[str, Any],
    ) -> Curriculum:
        connection = self.connect()
        now = utc_now()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM ai_curricula WHERE id = ? AND user_id = ?",
                (curriculum_id, int(user_id)),
            ).fetchone()
            if row is None:
                raise KeyError("Curriculum not found")
            current = CurriculumStatus(row["status"])
            if current not in {CurriculumStatus.DRAFT, CurriculumStatus.VALIDATED}:
                raise CurriculumStateError(f"Cannot validate curriculum in {current.value} state")
            valid = bool(validation_result.get("valid"))
            target = CurriculumStatus.VALIDATED if valid else CurriculumStatus.REJECTED
            connection.execute(
                """
                UPDATE ai_curricula
                SET status = ?, validation_result_json = ?, validated_at = ?,
                    rejected_at = CASE WHEN ? = 'rejected' THEN ? ELSE rejected_at END
                WHERE id = ? AND user_id = ?
                """,
                (
                    target.value,
                    self._json(validation_result),
                    now,
                    target.value,
                    now,
                    curriculum_id,
                    int(user_id),
                ),
            )
            if current is not target:
                self._insert_event(
                    connection,
                    curriculum_id=curriculum_id,
                    user_id=user_id,
                    from_status=current.value,
                    to_status=target.value,
                    reason="deterministic_validation",
                    metadata={"valid": valid},
                    created_at=now,
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_curriculum(user_id, curriculum_id)
        if stored is None:
            raise RuntimeError("Validated curriculum disappeared")
        return stored

    def publish(self, *, user_id: int, curriculum_id: str) -> Curriculum:
        connection = self.connect()
        now = utc_now()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM ai_curricula WHERE id = ? AND user_id = ?",
                (curriculum_id, int(user_id)),
            ).fetchone()
            if row is None:
                raise KeyError("Curriculum not found")
            current = CurriculumStatus(row["status"])
            if current is CurriculumStatus.PUBLISHED:
                connection.rollback()
                existing = self.get_curriculum(user_id, curriculum_id)
                if existing is None:
                    raise RuntimeError("Published curriculum disappeared")
                return existing
            if current is not CurriculumStatus.VALIDATED:
                raise CurriculumStateError("Only a validated curriculum can be published")

            previous_rows = connection.execute(
                """
                SELECT id FROM ai_curricula
                WHERE user_id = ? AND subject = ? AND status = 'published' AND id <> ?
                """,
                (int(user_id), row["subject"], curriculum_id),
            ).fetchall()
            for previous in previous_rows:
                connection.execute(
                    """
                    UPDATE ai_curricula
                    SET status = 'superseded', superseded_at = ?
                    WHERE id = ? AND user_id = ? AND status = 'published'
                    """,
                    (now, previous["id"], int(user_id)),
                )
                self._insert_event(
                    connection,
                    curriculum_id=previous["id"],
                    user_id=user_id,
                    from_status=CurriculumStatus.PUBLISHED.value,
                    to_status=CurriculumStatus.SUPERSEDED.value,
                    reason="new_curriculum_published",
                    metadata={"replacement_curriculum_id": curriculum_id},
                    created_at=now,
                )
            connection.execute(
                """
                UPDATE ai_curricula
                SET status = 'published', published_at = ?
                WHERE id = ? AND user_id = ? AND status = 'validated'
                """,
                (now, curriculum_id, int(user_id)),
            )
            self._insert_event(
                connection,
                curriculum_id=curriculum_id,
                user_id=user_id,
                from_status=CurriculumStatus.VALIDATED.value,
                to_status=CurriculumStatus.PUBLISHED.value,
                reason="application_publish",
                created_at=now,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_curriculum(user_id, curriculum_id)
        if stored is None:
            raise RuntimeError("Published curriculum disappeared")
        return stored

    def get_validation_result(
        self,
        user_id: int,
        curriculum_id: str,
    ) -> Optional[dict[str, Any]]:
        connection = self.connect()
        try:
            row = connection.execute(
                """
                SELECT validation_result_json FROM ai_curricula
                WHERE id = ? AND user_id = ?
                """,
                (curriculum_id, int(user_id)),
            ).fetchone()
            return json.loads(row[0]) if row and row[0] else None
        finally:
            connection.close()
