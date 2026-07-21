"""SQLite persistence and integrity checks for production curriculum quizzes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
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
        """Persist the current quiz definition without breaking old attempts.

        ``curriculum_quiz_sessions`` stores a complete immutable snapshot, and
        submitted attempts store their own review.  Because of that, refreshing
        the reusable per-lesson quiz template is safe: already-started attempts
        keep the exact questions they received.

        Earlier versions treated any same-schema content change as a conflict.
        A regenerated lesson or a grading hotfix could therefore make the quiz
        page return HTTP 409 before it even opened.  This method now repairs and
        refreshes the template in place while preserving its database identity.
        """

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

        # The unique lesson identity can outlive a quiz-ID algorithm change.
        # Keep the existing primary key so old sessions and attempts retain
        # valid foreign keys, then write the new content under that identity.
        if row["id"] != quiz.id:
            quiz = replace(quiz, id=row["id"])
            payload = quiz.to_dict(include_answer_key=True)
            digest = content_hash(payload)

        try:
            stored = self.quiz_from_row(row)
        except CurriculumQuizPersistenceError:
            # A damaged or legacy payload is recoverable because the canonical
            # quiz can be rebuilt from the server-authoritative lesson.
            stored = None

        if stored is not None and stored.to_dict() == quiz.to_dict():
            return stored

        cursor = connection.execute(
            """
            UPDATE curriculum_quizzes
            SET subject = ?, content_hash = ?, content_json = ?, schema_version = ?,
                generation_source = ?
            WHERE id = ? AND user_id = ?
              AND curriculum_id = ? AND curriculum_unit_id = ? AND lesson_id = ?
            """,
            (
                quiz.subject, digest, canonical_json(payload), quiz.schema_version,
                quiz.generation_source, quiz.id, int(user_id), quiz.curriculum_id,
                quiz.curriculum_unit_id, quiz.lesson_id,
            ),
        )
        if cursor.rowcount != 1:
            raise CurriculumQuizPersistenceError("Quiz template refresh did not update exactly one row.")

        refreshed_row = connection.execute(
            "SELECT * FROM curriculum_quizzes WHERE id = ? AND user_id = ?",
            (quiz.id, int(user_id)),
        ).fetchone()
        if refreshed_row is None:
            raise CurriculumQuizPersistenceError("Refreshed quiz could not be read back.")
        refreshed = self.quiz_from_row(refreshed_row)
        if refreshed.to_dict() != quiz.to_dict():
            raise CurriculumQuizPersistenceError("Refreshed quiz failed verification.")
        return refreshed

    @staticmethod
    def attempt_result_from_row(row: sqlite3.Row, *, idempotent: bool) -> QuizAttemptResult:
        try:
            review = tuple(json.loads(row["review_json"] or "[]"))
        except Exception as exc:
            raise CurriculumQuizPersistenceError("Stored attempt review is invalid.") from exc
        if len(review) != 12:
            raise CurriculumQuizPersistenceError("Stored attempt review must contain twelve questions.")

        correct_count = sum(
            1 for item in review
            if int(item.get("earned", 0)) == int(item.get("points", 0))
        )
        partial_count = sum(
            1 for item in review
            if 0 < int(item.get("earned", 0)) < int(item.get("points", 0))
        )
        incorrect_count = len(review) - correct_count - partial_count
        keys = set(row.keys())
        attempt_number = int(row["attempt_number"]) if "attempt_number" in keys else 1
        best_score = int(row["best_score"]) if "best_score" in keys else int(row["score"])
        previous_best = int(row["previous_best"]) if "previous_best" in keys else -1
        score = int(row["score"])
        return QuizAttemptResult(
            attempt_id=row["attempt_id"],
            attempt_token=row["attempt_token"],
            curriculum_unit_id=row["curriculum_unit_id"],
            score=score,
            total=int(row["total"]),
            passed=bool(row["passed"]),
            xp_awarded=int(row["xp_awarded"]),
            review=review,
            submitted_at=row["submitted_at"],
            idempotent=idempotent,
            attempt_number=attempt_number,
            best_score=best_score,
            is_personal_best=score > previous_best,
            correct_count=correct_count,
            partial_count=partial_count,
            incorrect_count=incorrect_count,
            remaining_to_pass=max(0, 18 - score),
        )

    @staticmethod
    def attempt_row_with_summary(
        connection: sqlite3.Connection,
        *,
        attempt_id: str | None = None,
        attempt_token: str | None = None,
    ) -> sqlite3.Row | None:
        """Read one attempt with stable attempt-order and best-score metadata."""

        if bool(attempt_id) == bool(attempt_token):
            raise ValueError("Provide exactly one attempt lookup key.")
        column = "attempt_id" if attempt_id else "attempt_token"
        value = attempt_id or attempt_token
        return connection.execute(
            f"""
            SELECT attempt.*,
                   (
                       SELECT COUNT(*)
                       FROM curriculum_quiz_attempts AS numbered
                       WHERE numbered.user_id = attempt.user_id
                         AND numbered.curriculum_id = attempt.curriculum_id
                         AND numbered.curriculum_unit_id = attempt.curriculum_unit_id
                         AND numbered.rowid <= attempt.rowid
                   ) AS attempt_number,
                   (
                       SELECT MAX(best.score)
                       FROM curriculum_quiz_attempts AS best
                       WHERE best.user_id = attempt.user_id
                         AND best.curriculum_id = attempt.curriculum_id
                         AND best.curriculum_unit_id = attempt.curriculum_unit_id
                   ) AS best_score,
                   COALESCE((
                       SELECT MAX(previous.score)
                       FROM curriculum_quiz_attempts AS previous
                       WHERE previous.user_id = attempt.user_id
                         AND previous.curriculum_id = attempt.curriculum_id
                         AND previous.curriculum_unit_id = attempt.curriculum_unit_id
                         AND previous.rowid < attempt.rowid
                   ), -1) AS previous_best
            FROM curriculum_quiz_attempts AS attempt
            WHERE attempt.{column} = ?
            """,
            (value,),
        ).fetchone()
