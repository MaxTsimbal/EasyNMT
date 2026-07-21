"""Server-authoritative production curriculum quiz delivery and grading."""
from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
import random
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from easynmt_ai import AIContext, AttachmentRef, FinalSolutionGradingItem, WrittenGradingItem
from easynmt_ai.lessons import Lesson
from easynmt_core.progress import (
    AssessmentSource,
    CurriculumUnitState,
    ServerVerifiedAssessmentResult,
)

from .builder import build_deterministic_quiz
from .errors import (
    CurriculumQuizAnswersIncomplete,
    CurriculumQuizNotAvailable,
    CurriculumQuizNotFound,
    CurriculumQuizOwnershipError,
    CurriculumQuizPersistenceError,
    CurriculumQuizPhotoError,
    CurriculumQuizPhotoUnreadable,
    CurriculumQuizPhotoUnavailable,
    CurriculumQuizSessionInvalid,
)
from .models import ProductionQuiz, QuizAttemptDelivery, QuizAttemptResult, QuizQuestion, QuizQuestionContext
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


@dataclass(frozen=True)
class _PreparedQuizSubmission:
    quiz: ProductionQuiz
    safe_answers: dict[str, str]
    snapshot_hash: str


@dataclass(frozen=True)
class _ResolvedQuestionGrade:
    earned: int
    correct: bool
    feedback: str
    answer: str
    source: str = "server"
    confidence: str = "deterministic"
    first_error: str = ""
    next_step: str = ""
    criteria: tuple[dict[str, object], ...] = ()
    submission_mode: str = "text"
    image_quality: str = "not_provided"
    transcription: str = ""


class CurriculumQuizService:
    SESSION_HOURS = 24

    def __init__(
        self,
        repository: CurriculumQuizRepository,
        progress_service,
        *,
        written_grader=None,
        final_solution_grader=None,
        logger=None,
    ):
        self.repository = repository
        self.progress_service = progress_service
        self.written_grader = written_grader
        self.final_solution_grader = final_solution_grader
        self.logger = logger

    @staticmethod
    def _parse_utc(value: object) -> datetime:
        """Parse SQLite ISO timestamps into timezone-aware UTC datetimes."""

        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp is empty")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _draft_from_row(row) -> dict[str, str]:
        try:
            payload = json.loads(row["answers_json"]) if row else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, (str, int, float))
        }

    @staticmethod
    def _snapshot_from_session(row) -> ProductionQuiz:
        payload = json.loads(row["quiz_snapshot_json"])
        if content_hash(payload) != row["quiz_snapshot_hash"]:
            raise CurriculumQuizPersistenceError("Quiz snapshot integrity check failed.")
        return ProductionQuiz.from_dict(payload)

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
                grading_mode=question.grading_mode,
                primary_answers=question.primary_answers,
                secondary_answers=question.secondary_answers,
                feedback_hint=question.feedback_hint,
                instruction=question.instruction,
                task=question.task,
                answer_format=question.answer_format,
                skill=question.skill,
                source_text=question.source_text,
                input_placeholder=question.input_placeholder,
                scoring_parts=question.scoring_parts,
                review_tip=question.review_tip,
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
            count = connection.execute(
                """SELECT COUNT(*) AS total FROM curriculum_quiz_attempts
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?""",
                (int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id),
            ).fetchone()["total"]
            now = datetime.now(timezone.utc)
            connection.execute(
                "DELETE FROM curriculum_quiz_sessions WHERE user_id = ? AND submitted_at IS NULL AND expires_at < ?",
                (int(user_id), now.isoformat(timespec="seconds")),
            )

            draft_row = connection.execute(
                """SELECT answers_json FROM curriculum_quiz_drafts
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?""",
                (int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id),
            ).fetchone()
            draft = self._draft_from_row(draft_row)

            # Refreshes and parallel tabs should reopen the same unfinished
            # attempt.  Sessions older than a submitted attempt are skipped so
            # the learner still receives a fresh variant after completion.
            active_row = connection.execute(
                """
                SELECT session.*
                FROM curriculum_quiz_sessions AS session
                WHERE session.user_id = ?
                  AND session.curriculum_id = ?
                  AND session.curriculum_unit_id = ?
                  AND session.subject = ?
                  AND session.submitted_at IS NULL
                  AND session.expires_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM curriculum_quiz_attempts AS attempt
                      WHERE attempt.user_id = session.user_id
                        AND attempt.curriculum_id = session.curriculum_id
                        AND attempt.curriculum_unit_id = session.curriculum_unit_id
                        AND attempt.submitted_at > session.started_at
                  )
                ORDER BY session.started_at DESC
                LIMIT 1
                """,
                (
                    int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id,
                    subject, now.isoformat(timespec="seconds"),
                ),
            ).fetchone()
            if active_row is not None:
                try:
                    active_snapshot = self._snapshot_from_session(active_row)
                    if (
                        active_snapshot.curriculum_id != quiz.curriculum_id
                        or active_snapshot.curriculum_unit_id != quiz.curriculum_unit_id
                        or active_snapshot.subject != subject
                    ):
                        raise CurriculumQuizPersistenceError("Active quiz snapshot identity is invalid.")
                    active_expires = self._parse_utc(active_row["expires_at"])
                    connection.commit()
                    return QuizAttemptDelivery(
                        attempt_token=active_row["attempt_token"],
                        quiz=active_snapshot,
                        draft_answers=draft,
                        expires_at=active_expires.isoformat(timespec="seconds"),
                        attempt_count=int(count),
                    )
                except Exception as exc:
                    # A broken unfinished session must not brick the entire
                    # assessment. Remove only that disposable session and issue
                    # a clean server snapshot below.
                    connection.execute(
                        "DELETE FROM curriculum_quiz_sessions WHERE attempt_token = ? AND submitted_at IS NULL",
                        (active_row["attempt_token"],),
                    )
                    if self.logger:
                        self.logger.warning(
                            "Discarded invalid curriculum quiz session token=%s error=%s",
                            str(active_row["attempt_token"])[:12],
                            type(exc).__name__,
                        )

            attempt_token = secrets.token_urlsafe(36)
            # The variant changes after each submitted attempt and remains
            # stable across refreshes because the active session is reused.
            variant_seed = f"{int(user_id)}|{quiz.curriculum_unit_id}|{int(count) + 1}"
            variant = build_deterministic_quiz(lesson, variant_seed=variant_seed)
            if variant.id != quiz.id:
                # The repository may preserve a legacy DB primary key. Sessions
                # must reference that same row while keeping the fresh content.
                variant_payload = variant.to_dict(include_answer_key=True)
                variant_payload["id"] = quiz.id
                variant = ProductionQuiz.from_dict(variant_payload)
            snapshot = self._shuffle_public_quiz(variant, attempt_token)
            snapshot_payload = snapshot.to_dict(include_answer_key=True)
            expires_at = (now + timedelta(hours=self.SESSION_HOURS)).isoformat(timespec="seconds")
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
            connection.commit()
            return QuizAttemptDelivery(
                attempt_token=attempt_token,
                quiz=snapshot,
                draft_answers=draft,
                expires_at=expires_at,
                attempt_count=int(count),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _stem(token: str) -> str:
        value = token.lower().strip("'’-")
        suffixes = (
            "ування", "ювання", "ення", "ання", "яться", "ється", "ились", "алися",
            "ними", "ними", "ого", "ому", "ими", "ами", "ями", "ів", "їв", "еві",
            "ові", "ати", "ити", "увати", "ують", "юють", "ний", "на", "не", "ні",
            "ing", "ied", "ies", "ed", "es", "s",
        )
        for suffix in suffixes:
            if len(value) - len(suffix) >= 4 and value.endswith(suffix):
                return value[:-len(suffix)]
        return value

    @classmethod
    def _semantic_tokens(cls, value: object) -> tuple[str, ...]:
        result: list[str] = []
        for token in _normalize(value).split():
            if len(token) < 2 or token in STOPWORDS:
                continue
            stem = cls._stem(token)
            if stem and stem not in result:
                result.append(stem)
        return tuple(result)

    @staticmethod
    def _token_matches(left: str, right: str) -> bool:
        if left == right or left in right or right in left:
            return True
        return SequenceMatcher(None, left, right).ratio() >= 0.78

    @classmethod
    def _similarity(cls, answer: str, reference: str) -> float:
        answer_normalized = _normalize(answer)
        reference_normalized = _normalize(reference)
        if not answer_normalized or not reference_normalized:
            return 0.0
        if answer_normalized == reference_normalized:
            return 1.0
        if reference_normalized in answer_normalized:
            return 0.96
        answer_tokens = cls._semantic_tokens(answer_normalized)
        reference_tokens = cls._semantic_tokens(reference_normalized)
        if not reference_tokens:
            return SequenceMatcher(None, answer_normalized, reference_normalized).ratio()
        matched = 0
        used: set[int] = set()
        for reference_token in reference_tokens:
            for index, answer_token in enumerate(answer_tokens):
                if index in used:
                    continue
                if cls._token_matches(answer_token, reference_token):
                    used.add(index)
                    matched += 1
                    break
        coverage = matched / max(1, len(reference_tokens))
        precision = matched / max(1, len(answer_tokens))
        sequence = SequenceMatcher(None, answer_normalized, reference_normalized).ratio()
        return max(coverage * 0.75 + precision * 0.25, sequence * 0.72)

    @classmethod
    def _best_similarity(cls, answer: str, references) -> float:
        return max((cls._similarity(answer, item) for item in references if str(item).strip()), default=0.0)

    @classmethod
    def _hit_count(cls, answer: str, references, *, threshold: float = 0.58) -> int:
        return sum(1 for item in references if cls._similarity(answer, item) >= threshold)

    @staticmethod
    def _clean_rubric_segment(value: object) -> str:
        return re.sub(r"^\s*(?:[-•]|\(?\d{1,2}\)?\s*[).:\-])\s*", "", str(value or "")).strip(" \t,;|")

    @classmethod
    def _split_rubric_answer(cls, answer: str, expected_count: int) -> list[str]:
        """Split multi-part answers without punishing harmless formatting choices.

        Learners may use new lines, semicolons, commas, pipes, or write all
        numbered parts in one line, for example: ``1) goes 2) studied 3) was``.
        The order is still preserved because each rubric part is positional.
        """
        clean = str(answer or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not clean:
            return []

        numbered_pattern = re.compile(r"(?<!\w)\(?([1-9]|1[0-2])\)?\s*[).:\-]\s*")
        markers = list(numbered_pattern.finditer(clean))
        if len(markers) >= 2:
            numbered: list[str] = []
            for index, marker in enumerate(markers):
                end = markers[index + 1].start() if index + 1 < len(markers) else len(clean)
                segment = cls._clean_rubric_segment(clean[marker.end():end])
                if segment:
                    numbered.append(segment)
            if numbered:
                return numbered[:expected_count]

        separated = [
            cls._clean_rubric_segment(item)
            for item in re.split(r"\n+|[;|]+", clean)
            if cls._clean_rubric_segment(item)
        ]
        if len(separated) >= 2:
            return separated[:expected_count]

        comma_separated = [
            cls._clean_rubric_segment(item)
            for item in clean.split(",")
            if cls._clean_rubric_segment(item)
        ]
        if len(comma_separated) == expected_count:
            return comma_separated

        return [cls._clean_rubric_segment(clean)]

    @staticmethod
    def _rubric_form(value: object) -> str:
        # Ignore only harmless article differences. Keep auxiliaries and verb
        # spelling strict because each rubric part is worth a full point.
        return " ".join(
            token for token in _normalize(value).split()
            if token not in {"a", "an", "the"}
        )

    @classmethod
    def _best_reference(cls, candidate: str, alternatives) -> tuple[str, float]:
        candidate_form = cls._rubric_form(candidate)
        scored = []
        for reference in alternatives:
            reference_text = str(reference).strip()
            if not reference_text:
                continue
            reference_form = cls._rubric_form(reference_text)
            score = 1.0 if candidate_form == reference_form and candidate_form else SequenceMatcher(
                None, candidate_form, reference_form
            ).ratio()
            scored.append((reference_text, score))
        return max(scored, key=lambda item: item[1], default=("", 0.0))

    @classmethod
    def _rubric_feedback(cls, segments: list[str], scoring_parts) -> tuple[int, str]:
        earned = 0
        lines: list[str] = []
        for index, alternatives in enumerate(scoring_parts, start=1):
            candidate = segments[index - 1] if index <= len(segments) else ""
            reference, similarity = cls._best_reference(candidate, alternatives)
            if similarity >= 0.98:
                earned += 1
                lines.append(f"{index}. ✅ {candidate}")
                continue

            shown = candidate or "відповіді немає"
            if not candidate:
                reason = "Цю частину пропущено."
            elif SequenceMatcher(None, _normalize(candidate), _normalize(reference)).ratio() >= 0.58:
                reason = "Майже правильно, але перевір написання, форму слова або порядок слів."
            else:
                reason = "Відповідь не відповідає цій частині завдання."
            lines.append(f"{index}. ❌ {shown}\n   {reason}\n   Правильно: {reference}")

        total = len(scoring_parts)
        if earned == total:
            heading = f"Усі {total} частини правильні."
        elif earned:
            heading = f"Зараховано {earned} з {total} частин."
        else:
            heading = f"Поки не зараховано жодної з {total} частин."
        return earned, heading + "\n" + "\n".join(lines)

    @classmethod
    def _grade(cls, question: QuizQuestion, raw_answer: object) -> tuple[int, bool, str, str]:
        answer = str(raw_answer or "").strip()[:8000]
        if not answer:
            return 0, False, "Відповіді немає. Напиши хоча б коротку відповідь.", "Відповіді немає"
        if question.answer_type == "choice":
            correct = secrets.compare_digest(
                _normalize(answer).encode("utf-8"),
                _normalize(question.correct_answer).encode("utf-8"),
            )
            return (1 if correct else 0), correct, question.explanation if correct else question.feedback_hint, answer

        accepted_score = cls._best_similarity(answer, question.accepted_answers)
        primary = question.primary_answers or question.accepted_answers or (question.correct_answer,)
        secondary = question.secondary_answers
        primary_score = cls._best_similarity(answer, primary)
        secondary_score = cls._best_similarity(answer, secondary)
        primary_hits = cls._hit_count(answer, primary)
        secondary_hits = cls._hit_count(answer, secondary)
        mode = question.grading_mode
        custom_feedback = ""

        if mode == "legacy":
            required = {_normalize(item) for item in question.keywords if _normalize(item)}
            answer_tokens = _tokens(answer)
            required_tokens = set().union(*(_tokens(item) for item in required)) if required else set()
            if not required_tokens:
                required_tokens = _tokens(question.correct_answer)
            evidence = len(answer_tokens & required_tokens) / max(1, len(required_tokens))
            if question.points == 2:
                earned = 2 if evidence >= 0.7 else 1 if evidence >= 0.3 else 0
            else:
                earned = 3 if evidence >= 0.72 else 2 if evidence >= 0.45 else 1 if evidence >= 0.22 else 0
        elif mode == "concept":
            # These prompts ask for one correct meaning or use case, not a copy of
            # the reference paragraph. One strong idea in the learner's own words
            # is therefore enough for full credit.
            earned = 2 if accepted_score >= 0.62 or primary_hits >= 1 or primary_score >= 0.46 else 1 if primary_score >= 0.28 else 0
        elif mode == "two_part":
            first = primary_score >= 0.62
            second = secondary_score >= 0.68
            earned = int(first) + int(second)
        elif mode == "any_valid":
            earned = 2 if accepted_score >= 0.44 or primary_score >= 0.44 else 1 if accepted_score >= 0.25 or primary_score >= 0.25 else 0
        elif mode == "exact":
            # Sentence transformations, word order, translation and gap tasks.
            # Punctuation and case do not matter; a nearly correct structure can
            # still receive one point instead of being treated as entirely wrong.
            exact = any(
                _normalize(answer) == _normalize(item)
                for item in question.accepted_answers
                if str(item).strip()
            )
            if exact or accepted_score >= 0.92:
                earned = question.points
            elif accepted_score >= 0.58 or primary_score >= 0.58:
                earned = max(1, question.points - 1)
            else:
                earned = 0
        elif mode == "rubric":
            # Each part is graded independently, but formatting is flexible:
            # new lines, semicolons, commas and one-line numbering are accepted.
            segments = cls._split_rubric_answer(answer, len(question.scoring_parts))
            earned, custom_feedback = cls._rubric_feedback(segments, question.scoring_parts)
        elif mode == "solution":
            final_is_present = primary_score >= 0.72 or accepted_score >= 0.9
            answer_token_set = set(cls._semantic_tokens(answer))
            primary_token_set = {
                token for item in primary for token in cls._semantic_tokens(item)
            }
            extra_tokens = answer_token_set - primary_token_set
            reasoning_is_present = bool(extra_tokens) and (
                secondary_score >= 0.52 or secondary_hits >= 1
            )
            earned = (2 if final_is_present else 0) + (1 if reasoning_is_present else 0)
            if not final_is_present and reasoning_is_present:
                earned = 1
        elif mode in {"correction", "verification"}:
            main_is_present = primary_score >= 0.58 or accepted_score >= 0.86
            answer_token_set = set(cls._semantic_tokens(answer))
            primary_token_set = {
                token for item in primary for token in cls._semantic_tokens(item)
            }
            extra_tokens = answer_token_set - primary_token_set
            support_is_present = bool(extra_tokens) and secondary_score >= 0.68
            earned = (2 if main_is_present else 0) + (1 if support_is_present else 0)
            if not main_is_present and support_is_present:
                earned = 1
        else:
            earned = 0

        earned = max(0, min(question.points, int(earned)))
        if custom_feedback:
            feedback = custom_feedback
        elif earned == question.points:
            feedback = "Правильно. " + question.explanation
        elif earned > 0:
            feedback = f"Є правильна частина, за неї нараховано {earned} з {question.points}. {question.feedback_hint}"
        else:
            feedback = "Поки не зараховано. " + question.feedback_hint
        return earned, earned == question.points, feedback, answer

    @staticmethod
    def _safe_submission_answers(quiz: ProductionQuiz, answers: Mapping[str, object]) -> dict[str, str]:
        allowed = {question.id for question in quiz.questions}
        safe = {
            str(key): str(value)[:8000]
            for key, value in dict(answers or {}).items()
            if str(key) in allowed and isinstance(value, (str, int, float))
        }
        return {key: value for key, value in safe.items() if value.strip()}

    def _validated_session_quiz(
        self,
        connection,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        attempt_token: str,
        now: datetime,
    ) -> tuple[object, ProductionQuiz]:
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
        if self._parse_utc(session_row["expires_at"]) <= now:
            raise CurriculumQuizSessionInvalid("Quiz attempt has expired.")
        try:
            quiz = self._snapshot_from_session(session_row)
        except CurriculumQuizPersistenceError:
            raise
        except Exception as exc:
            raise CurriculumQuizPersistenceError("Stored quiz snapshot is invalid.") from exc
        return session_row, quiz

    @staticmethod
    def _save_submission_draft(connection, *, user_id: int, quiz: ProductionQuiz, answers: Mapping[str, str]) -> None:
        connection.execute(
            """
            INSERT INTO curriculum_quiz_drafts (
                user_id, curriculum_id, curriculum_unit_id, answers_json, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, curriculum_id, curriculum_unit_id) DO UPDATE SET
                answers_json = excluded.answers_json,
                updated_at = excluded.updated_at
            """,
            (
                int(user_id), quiz.curriculum_id, quiz.curriculum_unit_id,
                canonical_json(dict(answers)), utc_now(),
            ),
        )

    def _prepare_submission(
        self,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        attempt_token: str,
        answers: Mapping[str, object],
        final_attachment: AttachmentRef | None = None,
    ) -> QuizAttemptResult | _PreparedQuizSubmission:
        """Validate and preserve answers before any potentially slow AI call.

        The transaction ends before written grading begins, so an OpenAI request
        never holds SQLite's write lock. A completed draft remains recoverable if
        the provider times out or the worker restarts before finalization.
        """

        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = self.repository.attempt_row_with_summary(
                connection,
                attempt_token=attempt_token,
            )
            if existing is not None:
                if int(existing["user_id"]) != int(user_id):
                    raise CurriculumQuizOwnershipError("Attempt belongs to another learner.")
                connection.commit()
                return self.repository.attempt_result_from_row(existing, idempotent=True)

            now = datetime.now(timezone.utc)
            session_row, quiz = self._validated_session_quiz(
                connection,
                user_id=user_id,
                subject=subject,
                curriculum_unit_id=curriculum_unit_id,
                attempt_token=attempt_token,
                now=now,
            )
            safe_answers = self._safe_submission_answers(quiz, answers)
            if final_attachment is not None and getattr(final_attachment, "kind", "") != "image":
                raise CurriculumQuizPhotoError("Завдання №12 підтримує лише зображення.")
            missing_questions = tuple(
                index
                for index, question in enumerate(quiz.questions, start=1)
                if not safe_answers.get(question.id, "").strip()
                and not (index == 12 and final_attachment is not None)
            )
            self._save_submission_draft(
                connection,
                user_id=user_id,
                quiz=quiz,
                answers=safe_answers,
            )
            connection.commit()
            if missing_questions:
                raise CurriculumQuizAnswersIncomplete(missing_questions)
            return _PreparedQuizSubmission(
                quiz=quiz,
                safe_answers=safe_answers,
                snapshot_hash=str(session_row["quiz_snapshot_hash"]),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _looks_like_grading_injection(answer: str) -> bool:
        lowered = str(answer or "").lower()
        markers = (
            "ignore previous", "ignore all", "system prompt", "award me", "give me points",
            "give full credit", "score this", "оцінюй мене", "постав мені", "дай мені бали",
            "нарахуй бали", "постав 3", "постав 2", "ігноруй поперед",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _ai_feedback(grade, *, earned: int, points: int) -> str:
        if earned == points:
            heading = "Правильно."
        elif earned:
            heading = f"Зараховано {earned} з {points} балів."
        else:
            heading = "Поки не зараховано."
        lines = [heading, grade.summary]
        for criterion in grade.criteria:
            icon = "✅" if criterion.passed else "❌"
            lines.append(f"{icon} {criterion.label}: {criterion.evidence}")
        if grade.first_error:
            lines.append(f"Перша неточність: {grade.first_error}")
        if grade.next_step:
            lines.append(f"Що зробити далі: {grade.next_step}")
        return "\n".join(line for line in lines if str(line).strip())

    def _resolve_question_grades(
        self,
        *,
        user_id: int,
        subject: str,
        quiz: ProductionQuiz,
        answers: Mapping[str, str],
        final_attachment: AttachmentRef | None = None,
    ) -> dict[str, _ResolvedQuestionGrade]:
        """Combine deterministic grading, written AI grading, and Q12 vision grading."""

        resolved: dict[str, _ResolvedQuestionGrade] = {}
        candidates: list[WrittenGradingItem] = []
        for index, question in enumerate(quiz.questions, start=1):
            earned, correct, feedback, answer = self._grade(question, answers.get(question.id))
            source = "server"
            if 5 <= index <= 11:
                source = "server-confirmed" if earned == question.points else "server-fallback"
            elif index == 12:
                source = "server-final-task"
            resolved[question.id] = _ResolvedQuestionGrade(
                earned=earned,
                correct=correct,
                feedback=feedback,
                answer=answer,
                source=source,
            )
            if not 5 <= index <= 11 or earned == question.points:
                continue
            if self._looks_like_grading_injection(answer):
                resolved[question.id] = _ResolvedQuestionGrade(
                    earned=earned,
                    correct=correct,
                    feedback=feedback,
                    answer=answer,
                    source="server-guarded",
                    confidence="guarded",
                    first_error="Відповідь містить мета-інструкції замість виконання завдання.",
                    next_step="Прибери прохання про оцінку й напиши саме розв’язання або відповідь.",
                )
                continue
            candidates.append(WrittenGradingItem(
                question_id=question.id,
                number=index,
                max_points=question.points,
                grading_mode=question.grading_mode,
                prompt=question.prompt,
                instruction=question.instruction,
                task=question.task,
                answer_format=question.answer_format,
                skill=question.skill,
                source_text=question.source_text,
                correct_answer=question.correct_answer,
                accepted_answers=question.accepted_answers,
                primary_answers=question.primary_answers,
                secondary_answers=question.secondary_answers,
                scoring_parts=question.scoring_parts,
                student_answer=answer,
            ))

        grader = self.written_grader
        if not candidates or grader is None or not bool(getattr(grader, "enabled", False)):
            return self._resolve_final_solution_grade(
                user_id=user_id, subject=subject, quiz=quiz, answers=answers,
                resolved=resolved, final_attachment=final_attachment,
            )

        try:
            ai_result = grader.grade(
                context=AIContext(
                    user_id=int(user_id),
                    subject=subject,
                    available_tokens=int(getattr(grader, "max_output_tokens", 2600)),
                    metadata={
                        "quiz_id": quiz.id,
                        "curriculum_unit_id": quiz.curriculum_unit_id,
                        "question_range": "5-11",
                    },
                ),
                items=tuple(candidates),
            )
        except Exception:
            if self.logger:
                self.logger.exception(
                    "Unexpected written grading failure quiz_id=%s user_id=%s",
                    quiz.id,
                    int(user_id),
                )
            return self._resolve_final_solution_grade(
                user_id=user_id, subject=subject, quiz=quiz, answers=answers,
                resolved=resolved, final_attachment=final_attachment,
            )

        if not getattr(ai_result, "success", False):
            if self.logger:
                error = getattr(ai_result, "error", None)
                self.logger.warning(
                    "Written grading fell back quiz_id=%s user_id=%s error=%s",
                    quiz.id,
                    int(user_id),
                    getattr(getattr(error, "code", None), "value", "unknown"),
                )
            return self._resolve_final_solution_grade(
                user_id=user_id, subject=subject, quiz=quiz, answers=answers,
                resolved=resolved, final_attachment=final_attachment,
            )

        for grade in ai_result.value.grades:
            deterministic = resolved[grade.question_id]
            if grade.confidence == "low":
                continue
            if grade.confidence == "medium":
                earned = max(deterministic.earned, grade.awarded_points)
                source = "ai-assisted"
            else:
                earned = grade.awarded_points
                source = "ai"
            earned = max(0, min(grade.max_points, int(earned)))
            resolved[grade.question_id] = _ResolvedQuestionGrade(
                earned=earned,
                correct=earned == grade.max_points,
                feedback=self._ai_feedback(grade, earned=earned, points=grade.max_points),
                answer=deterministic.answer,
                source=source,
                confidence=grade.confidence,
                first_error=grade.first_error,
                next_step=grade.next_step,
                criteria=tuple(criterion.to_dict() for criterion in grade.criteria),
            )

        return self._resolve_final_solution_grade(
            user_id=user_id,
            subject=subject,
            quiz=quiz,
            answers=answers,
            resolved=resolved,
            final_attachment=final_attachment,
        )

    def _resolve_final_solution_grade(
        self,
        *,
        user_id: int,
        subject: str,
        quiz: ProductionQuiz,
        answers: Mapping[str, str],
        resolved: dict[str, _ResolvedQuestionGrade],
        final_attachment: AttachmentRef | None,
    ) -> dict[str, _ResolvedQuestionGrade]:
        question = quiz.questions[11]
        deterministic = resolved[question.id]
        student_text = str(answers.get(question.id) or "").strip()
        has_photo = final_attachment is not None
        grader = self.final_solution_grader

        if not has_photo and self._looks_like_grading_injection(student_text):
            resolved[question.id] = _ResolvedQuestionGrade(
                earned=deterministic.earned,
                correct=deterministic.correct,
                feedback=deterministic.feedback,
                answer=student_text,
                source="server-guarded",
                confidence="guarded",
                first_error="Відповідь містить мета-інструкції замість виконання завдання.",
                next_step="Прибери прохання про оцінку й напиши саме розв’язання.",
            )
            return resolved

        if grader is None or not bool(getattr(grader, "enabled", False)):
            if has_photo and not student_text:
                raise CurriculumQuizPhotoUnavailable(
                    "Easy не може перевірити фото прямо зараз. Додай текстове розв’язання або спробуй пізніше."
                )
            if has_photo:
                resolved[question.id] = _ResolvedQuestionGrade(
                    earned=deterministic.earned,
                    correct=deterministic.correct,
                    feedback=(
                        deterministic.feedback
                        + "\nФото було отримано, але оцінка виконана за текстовою відповіддю, бо vision-перевірка недоступна."
                    ),
                    answer=(student_text or "Фото розв’язання"),
                    source="server-text-fallback",
                    confidence="deterministic",
                    submission_mode="photo_and_text",
                    image_quality="unavailable",
                )
            return resolved

        item = FinalSolutionGradingItem(
            question_id=question.id,
            number=12,
            max_points=question.points,
            grading_mode=question.grading_mode,
            prompt=question.prompt,
            instruction=question.instruction,
            task=question.task,
            answer_format=question.answer_format,
            skill=question.skill,
            source_text=question.source_text,
            correct_answer=question.correct_answer,
            accepted_answers=question.accepted_answers,
            primary_answers=question.primary_answers,
            secondary_answers=question.secondary_answers,
            scoring_parts=question.scoring_parts,
            student_text=student_text,
        )
        try:
            ai_result = grader.grade(
                context=AIContext(
                    user_id=int(user_id),
                    subject=subject,
                    available_tokens=int(getattr(grader, "max_output_tokens", 1800)),
                    metadata={
                        "quiz_id": quiz.id,
                        "curriculum_unit_id": quiz.curriculum_unit_id,
                        "question_number": 12,
                        "has_photo": has_photo,
                    },
                ),
                item=item,
                attachment=final_attachment,
            )
        except Exception:
            if self.logger:
                self.logger.exception(
                    "Unexpected final solution grading failure quiz_id=%s user_id=%s",
                    quiz.id, int(user_id),
                )
            if has_photo and not student_text:
                raise CurriculumQuizPhotoUnavailable(
                    "Фото не вдалося перевірити. Перефотографуй або додай текстове розв’язання."
                )
            return resolved

        if not getattr(ai_result, "success", False):
            if self.logger:
                error = getattr(ai_result, "error", None)
                self.logger.warning(
                    "Final solution grading fell back quiz_id=%s user_id=%s error=%s",
                    quiz.id, int(user_id),
                    getattr(getattr(error, "code", None), "value", "unknown"),
                )
            if has_photo and not student_text:
                raise CurriculumQuizPhotoUnavailable(
                    "Фото зараз не вдалося перевірити. Додай текстове розв’язання або спробуй пізніше."
                )
            return resolved

        grade = ai_result.value
        if has_photo and grade.image_quality == "unreadable" and not student_text:
            raise CurriculumQuizPhotoUnreadable(
                "Фото завдання №12 нечітке. Зніми аркуш рівно, при доброму освітленні, або додай текст."
            )
        if grade.confidence == "low":
            if has_photo and not student_text:
                raise CurriculumQuizPhotoUnavailable(
                    "Easy не зміг упевнено прочитати розв’язання. Перефотографуй або додай текст."
                )
            if student_text:
                answer_parts = []
                if has_photo:
                    answer_parts.append("Фото розв’язання завантажено, але не використано через низьку впевненість")
                answer_parts.append(f"Текст: {student_text}")
                resolved[question.id] = _ResolvedQuestionGrade(
                    earned=deterministic.earned,
                    correct=deterministic.correct,
                    feedback=(
                        deterministic.feedback
                        + ("\nEasy не зміг упевнено прочитати фото, тому бал визначено лише за текстом." if has_photo else "")
                    ),
                    answer="\n".join(answer_parts),
                    source="server-text-fallback",
                    confidence="deterministic",
                    submission_mode="photo_and_text" if has_photo else "text",
                    image_quality=grade.image_quality if has_photo else "not_provided",
                    transcription=grade.transcription,
                )
                return resolved
            earned = deterministic.earned
            source = "server-text-fallback"
        elif grade.confidence == "medium":
            earned = max(deterministic.earned, grade.awarded_points)
            source = "vision-assisted" if has_photo else "ai-assisted"
        else:
            earned = grade.awarded_points
            source = "vision" if has_photo else "ai-final"
        earned = max(0, min(3, int(earned)))

        answer_parts: list[str] = []
        if has_photo:
            answer_parts.append("Фото розв’язання завантажено")
        if student_text:
            answer_parts.append(f"Текст: {student_text}")
        if grade.transcription:
            answer_parts.append(f"Easy прочитав: {grade.transcription}")
        resolved[question.id] = _ResolvedQuestionGrade(
            earned=earned,
            correct=earned == 3,
            feedback=self._ai_feedback(grade, earned=earned, points=3),
            answer="\n".join(answer_parts) or deterministic.answer,
            source=source,
            confidence=grade.confidence,
            first_error=grade.first_error,
            next_step=grade.next_step,
            criteria=tuple(criterion.to_dict() for criterion in grade.criteria),
            submission_mode=grade.submission_mode,
            image_quality=grade.image_quality,
            transcription=grade.transcription,
        )
        return resolved

    def _finalize_submission(
        self,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        attempt_token: str,
        prepared: _PreparedQuizSubmission,
        grades: Mapping[str, _ResolvedQuestionGrade],
    ) -> QuizAttemptResult:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = self.repository.attempt_row_with_summary(
                connection,
                attempt_token=attempt_token,
            )
            if existing is not None:
                if int(existing["user_id"]) != int(user_id):
                    raise CurriculumQuizOwnershipError("Attempt belongs to another learner.")
                connection.commit()
                return self.repository.attempt_result_from_row(existing, idempotent=True)

            now = datetime.now(timezone.utc)
            session_row, quiz = self._validated_session_quiz(
                connection,
                user_id=user_id,
                subject=subject,
                curriculum_unit_id=curriculum_unit_id,
                attempt_token=attempt_token,
                now=now,
            )
            if str(session_row["quiz_snapshot_hash"]) != prepared.snapshot_hash:
                raise CurriculumQuizPersistenceError("Quiz snapshot changed during grading.")
            if quiz.to_dict(include_answer_key=True) != prepared.quiz.to_dict(include_answer_key=True):
                raise CurriculumQuizPersistenceError("Quiz snapshot no longer matches the graded copy.")

            if session_row["submitted_at"] is not None and self.logger:
                self.logger.warning(
                    "Recovering orphaned submitted quiz session token=%s user_id=%s",
                    str(attempt_token)[:12],
                    int(user_id),
                )

            score = 0
            review = []
            for index, question in enumerate(quiz.questions, start=1):
                grade = grades[question.id]
                score += grade.earned
                review.append({
                    "question_id": question.id,
                    "number": index,
                    "question": question.prompt,
                    "instruction": question.instruction,
                    "task": question.task,
                    "answer_format": question.answer_format,
                    "answer_type": question.answer_type,
                    "skill": question.skill,
                    "review_tip": question.review_tip or question.feedback_hint,
                    "user_answer": grade.answer,
                    "correct_answer": question.correct_answer,
                    "earned": grade.earned,
                    "points": question.points,
                    "is_correct": grade.correct,
                    "explanation": grade.feedback,
                    "grading_source": grade.source,
                    "grading_confidence": grade.confidence,
                    "first_error": grade.first_error,
                    "next_step": grade.next_step,
                    "criteria": list(grade.criteria),
                    "submission_mode": grade.submission_mode,
                    "image_quality": grade.image_quality,
                    "transcription": grade.transcription,
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
                    canonical_json({
                        **prepared.safe_answers,
                        **({quiz.questions[11].id: "[photo]"}
                           if grades[quiz.questions[11].id].submission_mode == "photo" else {}),
                    }), canonical_json(review), submitted_at,
                ),
            )
            connection.execute(
                "UPDATE curriculum_quiz_sessions SET submitted_at = ? WHERE attempt_token = ?",
                (submitted_at, attempt_token),
            )
            connection.execute(
                """DELETE FROM curriculum_quiz_drafts
                   WHERE user_id = ? AND curriculum_id = ? AND curriculum_unit_id = ?""",
                (int(user_id), quiz.curriculum_id, curriculum_unit_id),
            )
            row = self.repository.attempt_row_with_summary(connection, attempt_id=attempt_id)
            connection.commit()
            return self.repository.attempt_result_from_row(row, idempotent=False)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def submit_attempt(
        self,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        attempt_token: str,
        answers: Mapping[str, object],
        final_attachment: AttachmentRef | None = None,
    ) -> QuizAttemptResult:
        prepared = self._prepare_submission(
            user_id=user_id,
            subject=subject,
            curriculum_unit_id=curriculum_unit_id,
            attempt_token=attempt_token,
            answers=answers,
            final_attachment=final_attachment,
        )
        if isinstance(prepared, QuizAttemptResult):
            return prepared
        grades = self._resolve_question_grades(
            user_id=user_id,
            subject=subject,
            quiz=prepared.quiz,
            answers=prepared.safe_answers,
            final_attachment=final_attachment,
        )
        return self._finalize_submission(
            user_id=user_id,
            subject=subject,
            curriculum_unit_id=curriculum_unit_id,
            attempt_token=attempt_token,
            prepared=prepared,
            grades=grades,
        )


    def get_active_question_context(
        self,
        *,
        user_id: int,
        subject: str,
        curriculum_unit_id: str,
        attempt_token: str,
        question_id: str,
    ) -> QuizQuestionContext:
        """Return one active question after ownership and snapshot checks.

        This read path is used by restricted Easy help. It never serializes the
        answer key to the browser, but keeps the complete question server-side
        so the output guard can detect accidental answer leakage.
        """

        token = str(attempt_token or "").strip()
        requested_question_id = str(question_id or "").strip()
        if not token or not requested_question_id:
            raise CurriculumQuizSessionInvalid("Quiz help context is incomplete.")
        connection = self.repository.connect()
        try:
            row = connection.execute(
                "SELECT * FROM curriculum_quiz_sessions WHERE attempt_token = ?",
                (token,),
            ).fetchone()
            if row is None:
                raise CurriculumQuizSessionInvalid("Quiz attempt token is invalid.")
            if int(row["user_id"]) != int(user_id):
                raise CurriculumQuizOwnershipError("Quiz attempt belongs to another learner.")
            if row["curriculum_unit_id"] != curriculum_unit_id or row["subject"] != subject:
                raise CurriculumQuizSessionInvalid("Quiz attempt does not match this curriculum unit.")
            if row["submitted_at"] is not None:
                raise CurriculumQuizSessionInvalid("Quiz attempt has already been submitted.")
            expires_at = str(row["expires_at"])
            if self._parse_utc(expires_at) <= datetime.now(timezone.utc):
                raise CurriculumQuizSessionInvalid("Quiz attempt has expired.")
            try:
                quiz = self._snapshot_from_session(row)
            except CurriculumQuizPersistenceError:
                raise
            except Exception as exc:
                raise CurriculumQuizPersistenceError("Stored quiz snapshot is invalid.") from exc
            for index, question in enumerate(quiz.questions, start=1):
                if question.id == requested_question_id:
                    return QuizQuestionContext(
                        attempt_token=token,
                        quiz=quiz,
                        question=question,
                        question_number=index,
                        expires_at=expires_at,
                    )
            raise CurriculumQuizNotFound("Quiz question was not found in this attempt.")
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
            row = self.repository.attempt_row_with_summary(
                connection,
                attempt_id=attempt_id,
            )
            if row is None:
                raise CurriculumQuizNotFound("Quiz attempt was not found.")
            if int(row["user_id"]) != int(user_id):
                raise CurriculumQuizOwnershipError("Quiz attempt belongs to another learner.")
            return self.repository.attempt_result_from_row(row, idempotent=False)
        finally:
            connection.close()
