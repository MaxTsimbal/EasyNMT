"""SQLite persistence primitives for curriculum-unit progress."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from .errors import (
    CurriculumOwnershipError,
    CurriculumProgressNotFound,
    CurriculumUnitNotFound,
)
from .models import CurriculumUnitProgress, CurriculumUnitState, MasteryBand


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CurriculumProgressRepository:
    """Own progress schema and low-level owner-scoped persistence operations."""

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
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_curricula_id_user
                    ON ai_curricula(id, user_id);

                CREATE TABLE IF NOT EXISTS curriculum_unit_progress (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN (
                        'locked', 'available', 'in_progress', 'lesson_completed',
                        'assessment_required', 'completed', 'review_required'
                    )),
                    mastery_score REAL CHECK(
                        mastery_score IS NULL OR (mastery_score >= 0.0 AND mastery_score <= 1.0)
                    ),
                    mastery_band TEXT NOT NULL CHECK(mastery_band IN (
                        'unknown', 'introduced', 'developing', 'proficient',
                        'mastered', 'needs_review'
                    )),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                    xp_awarded INTEGER NOT NULL DEFAULT 0 CHECK(xp_awarded >= 0),
                    lesson_started_at TEXT,
                    lesson_completed_at TEXT,
                    assessment_required_at TEXT,
                    completed_at TEXT,
                    review_required_at TEXT,
                    last_activity_at TEXT NOT NULL,
                    source TEXT NOT NULL CHECK(source IN (
                        'curriculum', 'legacy_credit', 'prior_curriculum_credit',
                        'generation_mastery_credit'
                    )),
                    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, curriculum_id, curriculum_unit_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_checkpoint_progress (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('locked', 'available', 'completed')),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                    available_at TEXT,
                    completed_at TEXT,
                    last_activity_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, curriculum_id, checkpoint_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, checkpoint_id)
                        REFERENCES ai_curriculum_checkpoints(curriculum_id, checkpoint_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_topic_credits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    source TEXT NOT NULL CHECK(source IN (
                        'legacy_completion', 'prior_curriculum', 'generation_mastery_snapshot'
                    )),
                    source_reference TEXT NOT NULL,
                    mastery_score REAL NOT NULL CHECK(mastery_score >= 0.0 AND mastery_score <= 1.0),
                    credited_at TEXT NOT NULL,
                    UNIQUE(user_id, curriculum_id, topic_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_assessment_results (
                    attempt_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT,
                    checkpoint_id TEXT,
                    topic_id TEXT,
                    passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
                    score REAL NOT NULL CHECK(score >= 0),
                    max_score REAL NOT NULL CHECK(max_score > 0 AND score <= max_score),
                    normalized_score REAL NOT NULL CHECK(
                        normalized_score >= 0.0 AND normalized_score <= 1.0
                    ),
                    source TEXT NOT NULL CHECK(source IN (
                        'server_quiz', 'legacy_quiz', 'server_review',
                        'checkpoint_assessment'
                    )),
                    verified_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CHECK(
                        (curriculum_unit_id IS NOT NULL AND checkpoint_id IS NULL) OR
                        (curriculum_unit_id IS NULL AND checkpoint_id IS NOT NULL)
                    ),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, checkpoint_id)
                        REFERENCES ai_curriculum_checkpoints(curriculum_id, checkpoint_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_progress_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL CHECK(event_type IN (
                        'curriculum_progress_initialized', 'curriculum_unit_available',
                        'curriculum_unit_started', 'curriculum_unit_lesson_completed',
                        'curriculum_unit_assessment_required',
                        'curriculum_unit_assessment_passed',
                        'curriculum_unit_assessment_failed', 'curriculum_unit_completed',
                        'curriculum_unit_review_required', 'curriculum_unit_review_completed',
                        'curriculum_checkpoint_available', 'curriculum_checkpoint_passed',
                        'curriculum_checkpoint_failed', 'curriculum_unlocks_recalculated',
                        'curriculum_progress_migrated', 'curriculum_progress_rejected'
                    )),
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT,
                    checkpoint_id TEXT,
                    topic_id TEXT,
                    previous_state TEXT,
                    new_state TEXT,
                    reason TEXT NOT NULL,
                    attempt_id TEXT,
                    idempotency_key TEXT,
                    xp_delta INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (curriculum_id, user_id)
                        REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_curriculum_progress_active
                    ON curriculum_unit_progress(user_id, curriculum_id, state);
                CREATE INDEX IF NOT EXISTS idx_curriculum_progress_topic
                    ON curriculum_unit_progress(user_id, topic_id, state);
                CREATE INDEX IF NOT EXISTS idx_curriculum_progress_curriculum
                    ON curriculum_unit_progress(curriculum_id, state, curriculum_unit_id);
                CREATE INDEX IF NOT EXISTS idx_curriculum_checkpoint_active
                    ON curriculum_checkpoint_progress(user_id, curriculum_id, state);
                CREATE INDEX IF NOT EXISTS idx_curriculum_progress_events_lookup
                    ON curriculum_progress_events(user_id, curriculum_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_curriculum_assessment_unit
                    ON curriculum_assessment_results(
                        user_id, curriculum_id, curriculum_unit_id, verified_at
                    );
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def json_value(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    def curriculum_row(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM ai_curricula WHERE id = ?",
            (str(curriculum_id),),
        ).fetchone()
        if row is None:
            raise CurriculumProgressNotFound("Curriculum not found.")
        if int(row["user_id"]) != int(user_id):
            raise CurriculumOwnershipError("Curriculum does not belong to this user.")
        return row

    def unit_progress_row(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_unit_id: str,
        curriculum_id: Optional[str] = None,
    ) -> sqlite3.Row:
        params: list[object] = [str(curriculum_unit_id)]
        query = """
            SELECT p.*, c.status AS curriculum_status, c.subject,
                   u.position, u.prerequisite_topic_ids_json, u.reason_code
            FROM curriculum_unit_progress p
            JOIN ai_curricula c ON c.id = p.curriculum_id
            JOIN ai_curriculum_units u
              ON u.curriculum_id = p.curriculum_id AND u.unit_id = p.curriculum_unit_id
            WHERE p.curriculum_unit_id = ?
        """
        if curriculum_id is not None:
            query += " AND p.curriculum_id = ?"
            params.append(str(curriculum_id))
        rows = connection.execute(query, params).fetchall()
        if not rows:
            raise CurriculumUnitNotFound("Curriculum unit progress was not found.")
        owned = [row for row in rows if int(row["user_id"]) == int(user_id)]
        if not owned:
            raise CurriculumOwnershipError("Curriculum unit does not belong to this user.")
        if len(owned) > 1 and curriculum_id is None:
            active = [row for row in owned if row["curriculum_status"] == "published"]
            if len(active) == 1:
                return active[0]
            raise CurriculumUnitNotFound("Curriculum unit is ambiguous without a curriculum ID.")
        return owned[0]

    @staticmethod
    def progress_from_row(row: sqlite3.Row) -> CurriculumUnitProgress:
        return CurriculumUnitProgress(
            id=row["id"],
            user_id=int(row["user_id"]),
            curriculum_id=row["curriculum_id"],
            curriculum_unit_id=row["curriculum_unit_id"],
            topic_id=row["topic_id"],
            state=CurriculumUnitState(row["state"]),
            mastery_score=(
                None if row["mastery_score"] is None else float(row["mastery_score"])
            ),
            mastery_band=MasteryBand(row["mastery_band"]),
            attempt_count=int(row["attempt_count"]),
            xp_awarded=int(row["xp_awarded"]),
            lesson_started_at=row["lesson_started_at"],
            lesson_completed_at=row["lesson_completed_at"],
            assessment_required_at=row["assessment_required_at"],
            completed_at=row["completed_at"],
            review_required_at=row["review_required_at"],
            last_activity_at=row["last_activity_at"],
            source=row["source"],
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        event_key: str,
        event_type: str,
        user_id: int,
        curriculum_id: str,
        reason: str,
        curriculum_unit_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        attempt_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        xp_delta: int = 0,
        metadata: Optional[Mapping[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> bool:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO curriculum_progress_events (
                event_key, event_type, user_id, curriculum_id, curriculum_unit_id,
                checkpoint_id, topic_id, previous_state, new_state, reason,
                attempt_id, idempotency_key, xp_delta, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                event_type,
                int(user_id),
                curriculum_id,
                curriculum_unit_id,
                checkpoint_id,
                topic_id,
                previous_state,
                new_state,
                reason,
                attempt_id,
                idempotency_key,
                int(xp_delta),
                self.json_value(metadata or {}),
                created_at or utc_now(),
            ),
        )
        return cursor.rowcount == 1

    def get_progress(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        curriculum_id: Optional[str] = None,
    ) -> CurriculumUnitProgress:
        connection = self.connect()
        try:
            row = self.unit_progress_row(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
            )
            return self.progress_from_row(row)
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
            self.curriculum_row(
                connection,
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
            rows = connection.execute(
                """
                SELECT * FROM curriculum_progress_events
                WHERE user_id = ? AND curriculum_id = ?
                ORDER BY id
                """,
                (int(user_id), curriculum_id),
            ).fetchall()
            return [
                {
                    **dict(row),
                    "metadata": json.loads(row["metadata_json"] or "{}"),
                }
                for row in rows
            ]
        finally:
            connection.close()
