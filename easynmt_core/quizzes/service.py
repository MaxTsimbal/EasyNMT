"""Server-authoritative production curriculum quiz delivery and grading."""
from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Mapping

from easynmt_ai.lessons import Lesson
from easynmt_core.progress import (
    AssessmentSource,
    CurriculumUnitState,
    ServerVerifiedAssessmentResult,
)

from .builder import build_deterministic_quiz
from .errors import (
    CurriculumQuizConflict,
    CurriculumQuizNotAvailable,
    CurriculumQuizNotFound,
    CurriculumQuizOwnershipError,
    CurriculumQuizPersistenceError,
    CurriculumQuizSessionInvalid,
)
from .models import ProductionQuiz, QuizAttemptDelivery, QuizAttemptResult, QuizQuestion
from .repository import CurriculumQuizRepository, canonical_json, content_hash, utc_now


STOPWORDS = frozenset({
    "і", "й", "та", "у", "в", "на", "до", "з", "із", "за", "для", "що", "як", "це",
    "the", "a", "an", "to", "of", "in", "on", "and", "or", "is", "are", "be", "with",
})


def _normalize(value: object) -> str:
    return " ".join(re.findall(r"[\w’'+=°%./-]+", str(value or "").lower(), flags=re.UNICODE))


def _tokens(value: object) -> set[str]:
    return {
        word for word in _normalize(value).split()
        if len(word) >= 3 and word not in STOPWORDS
    }


class CurriculumQuizService:
    SESSION_HOURS = 24

    def __init__(self, repository: CurriculumQuizRepository, progress_service, *, logger=None):
        self.repository = repository
        self.progress_service = progress_service
        self.logger = logger

    @staticmethod
    def _shuffle_public_quiz(quiz: ProductionQuiz, attempt_token: str) -> ProductionQuiz:
        seeded = random.Random(hashlib.sha256(attempt_token.encode("utf-8")).digest())
        questions = []
        for question in quiz.questions:
            if question.answer_type != "choice":
                questions.append(question)
                continue
            options = list(question.options)
            seeded.shuffle(options)
            questions.append(QuizQuestion(
                id=question.id,
                prompt=question.prompt,
                answer_type=question.answer_type,
                options=tuple(options),
                correct_answer=question.correct_answer,
                accepted_answers=question.accepted_answers,
                keywords=question.keywords,
                explanation=question.explanation,
                points=question.points,
            ))
        return ProductionQuiz(
            id=quiz.id,
            curriculum_id=quiz.curriculum_id,
            curriculum_unit_id=quiz.curriculum_unit_id,
            topic_id=quiz.topic_id,
            lesson_id=quiz.lesson_id,
            subject=quiz.subject,
            title=quiz.title,
            questions=tuple(questions),
            pass_score=quiz.pass_score,
            max_score=quiz.max_score,
            schema_version=quiz.schema_version,
            generation_source=quiz.generation_source,
        )

    def start_attempt(self, *, user_id: int, subject: str, lesson: Lesson) -> QuizAttemptDelivery:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            progress = self.progress_service.get_active_unit_progress_in_transaction(
                connection,
                user_id=int(user_id),
                curriculum_unit_id=lesson.curriculum_unit_id,
                curriculum_id=lesson.curriculum_id,
                subject=subject,
            )
            if progress.state not in {
                CurriculumUnitState.ASSESSMENT_REQUIRED,
                CurriculumUnitState.COMPLETED,
            }:
                raise CurriculumQuizNotAvailable("Finish the lesson before starting its assessment.")
            if lesson.subject != subject:
                raise CurriculumQuizOwnershipError("Lesson subject does not match the active subject.")
            quiz = self.repository.save_quiz(
                connection,
                user_id=int(user_id),
                quiz=build_deterministic_quiz(lesson),
            )
            attempt_token = secrets.token_urlsafe(36)
            snapshot = self._shuffle_public_quiz(quiz, attempt_token)
            snapshot_payload = snapshot.to_dict(include_answer_key=True)
            now = datetime.now(timezone.utc)
            expires_at = (now + timedelta(hours=self.SESSION_HOURS)).isoformat(timespec="seconds")
            connection.execute(
                "DELETE FROM curriculum_quiz_sessions WHERE user_id = ? AND submitted_at IS NULL AND expires_at < ?",
                (int(user_id), now.isoformat(timespec="seconds")),
            )
            connection.execute(
                """
                INSERT INTO curriculum_quiz_sessions (
                    attempt_token, user_id, quiz_id, curriculum_id, curriculum_unit_id,
                    subject, quiz_snapshot_hash, quiz_snapshot_json, started_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_token, int(user_id), quiz.id, quiz.curriculum_id,
                    quiz.curriculum_unit_id, subject, content_hash(snapshot_payload),
                    canonical_json(snapshot_payload), now.isoformat(timespec="seconds"), expires_at,
                ),
            )
            draft_row = connection.execute(
                """SELECT answers_json FROM curriculum_quiz_drafts
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?""",
                (int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id),
            ).fetchone()
            try:
                draft = json.loads(draft_row["answers_json"]) if draft_row else {}
            except Exception:
                draft = {}
            count = connection.execute(
                """SELECT COUNT(*) AS total FROM curriculum_quiz_attempts
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?""",
                (int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id),
            ).fetchone()["total"]
            connection.commit()
            return QuizAttemptDelivery(
                attempt_token=attempt_token,
                quiz=snapshot,
                draft_answers={str(k): str(v) for k, v in draft.items() if isinstance(k, str)},
                expires_at=expires_at,
                attempt_count=int(count),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _grade(question: QuizQuestion, raw_answer: object) -> tuple[int, bool, str, str]:
        answer = str(raw_answer or "").strip()[:8000]
        if not answer:
            return 0, False, "Відповіді немає. Запиши хоча б перший змістовний крок.", "Відповіді немає"
        if question.answer_type == "choice":
            correct = secrets.compare_digest(_normalize(answer).encode("utf-8"), _normalize(question.correct_answer).encode("utf-8"))
            return (1 if correct else 0), correct, question.explanation, answer

        normalized = _normalize(answer)
        accepted = {_normalize(item) for item in question.accepted_answers}
        if normalized in accepted:
            return question.points, True, question.explanation, answer

        required = {_normalize(item) for item in question.keywords if _normalize(item)}
        answer_tokens = _tokens(answer)
        required_tokens = set().union(*(_tokens(item) for item in required)) if required else set()
        if not required_tokens:
            required_tokens = _tokens(question.correct_answer)
        overlap = len(answer_tokens & required_tokens) / max(1, len(required_tokens))
        reference_overlap = len(answer_tokens & _tokens(question.correct_answer)) / max(1, len(_tokens(question.correct_answer)))
        evidence = max(overlap, reference_overlap)
        if question.points == 2:
            earned = 2 if evidence >= 0.7 else 1 if evidence >= 0.3 else 0
        else:
            earned = 3 if evidence >= 0.72 else 2 if evidence >= 0.45 else 1 if evidence >= 0.22 else 0
        if earned == question.points:
            feedback = question.explanation
        elif earned:
            feedback = "Напрям правильний, але відповідь неповна. " + question.explanation
        else:
            feedback = "У відповіді немає ключових елементів із уроку. " + question.explanation
        return earned, earned == question.points, feedback, answer

    def submit_attempt(
        self,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        attempt_token: str,
        answers: Mapping[str, object],
    ) -> QuizAttemptResult:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM curriculum_quiz_attempts WHERE attempt_token = ?",
                (attempt_token,),
            ).fetchone()
            if existing is not None:
                if int(existing["user_id"]) != int(user_id):
                    raise CurriculumQuizOwnershipError("Attempt belongs to another learner.")
                connection.commit()
                return self.repository.attempt_result_from_row(existing, idempotent=True)

            session_row = connection.execute(
                "SELECT * FROM curriculum_quiz_sessions WHERE attempt_token = ?",
                (attempt_token,),
            ).fetchone()
            if session_row is None:
                raise CurriculumQuizSessionInvalid("Quiz attempt token is invalid.")
            if int(session_row["user_id"]) != int(user_id):
                raise CurriculumQuizOwnershipError("Quiz attempt belongs to another learner.")
            if session_row["curriculum_unit_id"] != curriculum_unit_id or session_row["subject"] != subject:
                raise CurriculumQuizSessionInvalid("Quiz attempt does not match this curriculum unit.")
            if session_row["submitted_at"] is not None:
                raise CurriculumQuizConflict("Quiz session was already submitted.")
            now = datetime.now(timezone.utc)
            expires = datetime.fromisoformat(session_row["expires_at"])
            if expires <= now:
                raise CurriculumQuizSessionInvalid("Quiz attempt has expired.")
            try:
                payload = json.loads(session_row["quiz_snapshot_json"])
                if content_hash(payload) != session_row["quiz_snapshot_hash"]:
                    raise CurriculumQuizPersistenceError("Quiz snapshot integrity check failed.")
                quiz = ProductionQuiz.from_dict(payload)
            except CurriculumQuizPersistenceError:
                raise
            except Exception as exc:
                raise CurriculumQuizPersistenceError("Stored quiz snapshot is invalid.") from exc

            allowed = {question.id for question in quiz.questions}
            safe_answers = {
                str(key): str(value)[:8000]
                for key, value in dict(answers or {}).items()
                if str(key) in allowed and isinstance(value, (str, int, float))
            }
            score = 0
            review = []
            for index, question in enumerate(quiz.questions, start=1):
                earned, correct, feedback, answer = self._grade(question, safe_answers.get(question.id))
                score += earned
                review.append({
                    "question_id": question.id,
                    "number": index,
                    "question": question.prompt,
                    "answer_type": question.answer_type,
                    "user_answer": answer,
                    "correct_answer": question.correct_answer,
                    "earned": earned,
                    "points": question.points,
                    "is_correct": correct,
                    "explanation": feedback,
                })
            passed = score >= quiz.pass_score
            attempt_id = f"attempt-{hashlib.sha256(attempt_token.encode('utf-8')).hexdigest()[:28]}"
            progress_before = self.progress_service.get_active_unit_progress_in_transaction(
                connection,
                user_id=int(user_id),
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=quiz.curriculum_id,
                subject=subject,
            )
            progress_after = progress_before
            if progress_before.state is CurriculumUnitState.ASSESSMENT_REQUIRED:
                verified = ServerVerifiedAssessmentResult(
                    passed=passed,
                    score=score,
                    max_score=quiz.max_score,
                    attempt_id=attempt_id,
                    verified_at=now,
                    source=AssessmentSource.SERVER_QUIZ,
                )
                progress_after = self.progress_service.record_assessment_result_in_transaction(
                    connection,
                    user_id=int(user_id),
                    curriculum_unit_id=curriculum_unit_id,
                    result=verified,
                    curriculum_id=quiz.curriculum_id,
                )
            elif progress_before.state is not CurriculumUnitState.COMPLETED:
                raise CurriculumQuizNotAvailable("Curriculum unit is not waiting for assessment.")
            xp_delta = max(0, int(progress_after.xp_awarded) - int(progress_before.xp_awarded))
            submitted_at = now.isoformat(timespec="seconds")
            connection.execute(
                """
                INSERT INTO curriculum_quiz_attempts (
                    attempt_id, attempt_token, user_id, quiz_id, curriculum_id,
                    curriculum_unit_id, subject, score, total, passed, xp_awarded,
                    answers_json, review_json, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id, attempt_token, int(user_id), quiz.id, quiz.curriculum_id,
                    curriculum_unit_id, subject, score, quiz.max_score, int(passed), xp_delta,
                    canonical_json(safe_answers), canonical_json(review), submitted_at,
                ),
            )
            connection.execute(
                "UPDATE curriculum_quiz_sessions SET submitted_at = ? WHERE attempt_token = ? AND submitted_at IS NULL",
                (submitted_at, attempt_token),
            )
            connection.execute(
                """DELETE FROM curriculum_quiz_drafts
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?""",
                (int(user_id), quiz.curriculum_id, curriculum_unit_id),
            )
            row = connection.execute(
                "SELECT * FROM curriculum_quiz_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            connection.commit()
            return self.repository.attempt_result_from_row(row, idempotent=False)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_draft(
        self,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        answers: Mapping[str, object],
    ) -> None:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            progress = self.progress_service.get_active_unit_progress_in_transaction(
                connection,
                user_id=int(user_id),
                curriculum_unit_id=curriculum_unit_id,
                subject=subject,
            )
            if progress.state not in {CurriculumUnitState.ASSESSMENT_REQUIRED, CurriculumUnitState.COMPLETED}:
                raise CurriculumQuizNotAvailable("Quiz draft is not available for this unit.")
            latest = connection.execute(
                """SELECT quiz_snapshot_json FROM curriculum_quiz_sessions
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?
                   ORDER BY started_at DESC LIMIT 1""",
                (int(user_id), progress.curriculum_id, curriculum_unit_id),
            ).fetchone()
            allowed: set[str] = set()
            if latest:
                try:
                    allowed = {item["id"] for item in json.loads(latest["quiz_snapshot_json"])["questions"]}
                except Exception:
                    allowed = set()
            safe = {
                str(key): str(value)[:8000]
                for key, value in dict(answers or {}).items()
                if str(key) in allowed and isinstance(value, (str, int, float))
            }
            connection.execute(
                """
                INSERT INTO curriculum_quiz_drafts (
                    user_id, curriculum_id, curriculum_unit_id, answers_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, curriculum_id, curriculum_unit_id) DO UPDATE SET
                    answers_json = excluded.answers_json,
                    updated_at = excluded.updated_at
                """,
                (int(user_id), progress.curriculum_id, curriculum_unit_id, canonical_json(safe), utc_now()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_result(self, *, user_id: int, attempt_id: str) -> QuizAttemptResult:
        connection = self.repository.connect()
        try:
            row = connection.execute(
                "SELECT * FROM curriculum_quiz_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise CurriculumQuizNotFound("Quiz attempt was not found.")
            if int(row["user_id"]) != int(user_id):
                raise CurriculumQuizOwnershipError("Quiz attempt belongs to another learner.")
            return self.repository.attempt_result_from_row(row, idempotent=False)
        finally:
            connection.close()
