"""SQLite persistence and integrity checks for production curriculum quizzes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .errors import CurriculumQuizPersistenceError
from .models import ProductionQuiz, QuizAttemptResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class CurriculumQuizRepository:
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
                CREATE TABLE IF NOT EXISTS curriculum_quizzes (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    lesson_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    generation_source TEXT NOT NULL CHECK(generation_source IN ('deterministic', 'openai')),
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, curriculum_id, curriculum_unit_id, lesson_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(curriculum_id, user_id) REFERENCES ai_curricula(id, user_id) ON DELETE CASCADE,
                    FOREIGN KEY(curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE,
                    FOREIGN KEY(lesson_id) REFERENCES curriculum_lessons(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_quiz_sessions (
                    attempt_token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    quiz_id TEXT NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    quiz_snapshot_hash TEXT NOT NULL,
                    quiz_snapshot_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    submitted_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(quiz_id) REFERENCES curriculum_quizzes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_quiz_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    attempt_token TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    quiz_id TEXT NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK(score >= 0 AND score <= 24),
                    total INTEGER NOT NULL CHECK(total = 24),
                    passed INTEGER NOT NULL CHECK(passed IN (0, 1)),
                    xp_awarded INTEGER NOT NULL DEFAULT 0 CHECK(xp_awarded >= 0),
                    answers_json TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(quiz_id) REFERENCES curriculum_quizzes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS curriculum_quiz_drafts (
                    user_id INTEGER NOT NULL,
                    curriculum_id TEXT NOT NULL,
                    curriculum_unit_id TEXT NOT NULL,
                    answers_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, curriculum_id, curriculum_unit_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(curriculum_id, curriculum_unit_id)
                        REFERENCES ai_curriculum_units(curriculum_id, unit_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_curriculum_quiz_attempts_owner_unit
                    ON curriculum_quiz_attempts(user_id, curriculum_id, curriculum_unit_id, submitted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_curriculum_quiz_sessions_owner_unit
                    ON curriculum_quiz_sessions(user_id, curriculum_unit_id, expires_at);
                """
            )
            connection.execute(
                "DELETE FROM curriculum_quiz_sessions WHERE submitted_at IS NULL AND expires_at < ?",
                (utc_now(),),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def quiz_from_row(row: sqlite3.Row) -> ProductionQuiz:
        try:
            payload = json.loads(row["content_json"])
            quiz = ProductionQuiz.from_dict(payload)
        except Exception as exc:
            raise CurriculumQuizPersistenceError("Stored quiz failed schema validation.") from exc
        if content_hash(payload) != row["content_hash"] or quiz.id != row["id"]:
            raise CurriculumQuizPersistenceError("Stored quiz integrity check failed.")
        return quiz

    def save_quiz(self, connection: sqlite3.Connection, *, user_id: int, quiz: ProductionQuiz) -> ProductionQuiz:
        payload = quiz.to_dict(include_answer_key=True)
        digest = content_hash(payload)
        connection.execute(
            """
            INSERT OR IGNORE INTO curriculum_quizzes (
                id, user_id, curriculum_id, curriculum_unit_id, lesson_id, subject,
                content_hash, content_json, schema_version, generation_source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quiz.id, int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id,
                quiz.lesson_id, quiz.subject, digest, canonical_json(payload),
                quiz.schema_version, quiz.generation_source, utc_now(),
            ),
        )
        row = connection.execute(
            """SELECT * FROM curriculum_quizzes
               WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ? AND lesson_id = ?""",
            (int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id, quiz.lesson_id),
        ).fetchone()
        if row is None:
            raise CurriculumQuizPersistenceError("Quiz could not be persisted.")
        stored = self.quiz_from_row(row)
        if stored.to_dict() != quiz.to_dict():
            raise CurriculumQuizPersistenceError("A different immutable quiz owns this lesson identity.")
        return stored

    @staticmethod
    def attempt_result_from_row(row: sqlite3.Row, *, idempotent: bool) -> QuizAttemptResult:
        try:
            review = tuple(json.loads(row["review_json"] or "[]"))
        except Exception as exc:
            raise CurriculumQuizPersistenceError("Stored attempt review is invalid.") from exc
        return QuizAttemptResult(
            attempt_id=row["attempt_id"],
            attempt_token=row["attempt_token"],
            curriculum_unit_id=row["curriculum_unit_id"],
            score=int(row["score"]),
            total=int(row["total"]),
            passed=bool(row["passed"]),
            xp_awarded=int(row["xp_awarded"]),
            review=review,
            submitted_at=row["submitted_at"],
            idempotent=idempotent,
        )
