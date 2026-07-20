"""Application service for generated curriculum lessons and completion evidence."""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from easynmt_ai.curriculum import MathTaxonomy, load_math_taxonomy
from easynmt_ai.engines import LessonEngine
from easynmt_ai.lessons import (
    Lesson,
    LessonGenerationRequest,
    LessonPrerequisite,
    validate_lesson,
)
from easynmt_ai.schemas import AIContext
from easynmt_core.progress import (
    CurriculumProgressService,
    CurriculumUnitState,
    LessonCompletionEvidence,
    LessonCompletionSource,
)

from .errors import (
    CurriculumLessonConflict,
    CurriculumLessonDeliveryInvalid,
    CurriculumLessonGenerationUnavailable,
    CurriculumLessonNotAvailable,
    CurriculumLessonPersistenceError,
)
from .models import LessonCompletionResult, LessonDeliveryResult
from .repository import CurriculumLessonRepository, content_hash, utc_now


READABLE_STATES = frozenset({
    CurriculumUnitState.IN_PROGRESS,
    CurriculumUnitState.LESSON_COMPLETED,
    CurriculumUnitState.ASSESSMENT_REQUIRED,
    CurriculumUnitState.COMPLETED,
})


class CurriculumLessonService:
    """Generate, persist, deliver, and verify lessons without owning progress.

    The service coordinates one Lesson Engine request with immutable SQLite
    persistence. Completion is delegated to ``CurriculumProgressService`` in
    the same transaction that consumes server-issued delivery evidence.
    """

    def __init__(
        self,
        repository: CurriculumLessonRepository,
        engine: LessonEngine,
        progress_service: CurriculumProgressService,
        *,
        taxonomy: Optional[MathTaxonomy] = None,
        logger: Optional[logging.Logger] = None,
        max_output_tokens: int = 6500,
    ) -> None:
        self.repository = repository
        self.engine = engine
        self.progress_service = progress_service
        self.taxonomy = taxonomy or load_math_taxonomy()
        self.logger = logger or logging.getLogger("easynmt.curriculum_lessons")
        self.max_output_tokens = max(2500, int(max_output_tokens))
        self._locks_guard = threading.Lock()
        self._generation_locks: dict[str, threading.Lock] = {}

    def _generation_lock(self, fingerprint: str) -> threading.Lock:
        with self._locks_guard:
            if len(self._generation_locks) > 1024:
                self._generation_locks = {
                    key: lock
                    for key, lock in self._generation_locks.items()
                    if lock.locked()
                }
            return self._generation_locks.setdefault(fingerprint, threading.Lock())

    @staticmethod
    def _assert_readable_state(state: CurriculumUnitState) -> None:
        if state not in READABLE_STATES:
            raise CurriculumLessonNotAvailable(
                "Start this curriculum unit before requesting its lesson."
            )

    def _request_and_context(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_unit_id: str,
        subject: str,
    ) -> tuple[LessonGenerationRequest, AIContext]:
        progress = self.progress_service.get_active_unit_progress_in_transaction(
            connection,
            user_id=user_id,
            curriculum_unit_id=curriculum_unit_id,
            subject=subject,
        )
        self._assert_readable_state(progress.state)
        row = connection.execute(
            """
            SELECT c.target_score, c.subject, c.status, u.*
            FROM ai_curriculum_units u
            JOIN ai_curricula c ON c.id = u.curriculum_id
            WHERE u.curriculum_id = ? AND u.unit_id = ? AND c.user_id = ?
            """,
            (progress.curriculum_id, curriculum_unit_id, int(user_id)),
        ).fetchone()
        if row is None:
            raise CurriculumLessonNotAvailable("Curriculum lesson source was not found.")
        if row["status"] != "published" or row["subject"] != subject:
            raise CurriculumLessonNotAvailable("Curriculum lesson is not active.")
        try:
            topic = self.taxonomy.topic(progress.topic_id)
            prerequisites = tuple(
                LessonPrerequisite(
                    topic_id=topic_id,
                    title=self.taxonomy.topic(topic_id).title_uk,
                )
                for topic_id in topic.prerequisite_topic_ids
            )
        except KeyError as exc:
            raise CurriculumLessonNotAvailable(
                "Curriculum lesson topic is not present in the active taxonomy."
            ) from exc

        progress_rows = connection.execute(
            """
            SELECT topic_id, state, mastery_score
            FROM curriculum_unit_progress
            WHERE user_id = ? AND curriculum_id = ?
            """,
            (int(user_id), progress.curriculum_id),
        ).fetchall()
        completed_topic_ids = tuple(
            item["topic_id"]
            for item in progress_rows
            if item["state"] == CurriculumUnitState.COMPLETED.value
        )
        mastery = {
            item["topic_id"]: float(item["mastery_score"])
            for item in progress_rows
            if item["mastery_score"] is not None
        }
        weaknesses = tuple(
            self.taxonomy.topics_by_id[item["topic_id"]].title_uk
            for item in progress_rows
            if item["mastery_score"] is not None
            and float(item["mastery_score"]) < float(row["mastery_target"])
            and item["topic_id"] in self.taxonomy.topics_by_id
        )
        xp_row = connection.execute(
            """
            SELECT xp FROM user_subject_progress WHERE user_id = ? AND subject = ?
            """,
            (int(user_id), subject),
        ).fetchone()
        context = AIContext(
            user_id=user_id,
            subject=subject,
            goal_score=int(row["target_score"]),
            known_weaknesses=weaknesses,
            xp=int(xp_row["xp"]) if xp_row else 0,
            language="uk",
            difficulty=row["difficulty"],
            available_tokens=self.max_output_tokens,
            completed_topic_ids=completed_topic_ids,
            mastery_by_topic=mastery,
            active_curriculum_id=progress.curriculum_id,
        )
        request = LessonGenerationRequest(
            lesson_id="pending-generation-identity",
            curriculum_id=progress.curriculum_id,
            curriculum_unit_id=curriculum_unit_id,
            topic_id=progress.topic_id,
            subject=subject,
            title=topic.title_uk,
            description=topic.description_uk,
            objectives=topic.learning_objectives,
            competencies=topic.competencies,
            prerequisites=prerequisites,
            difficulty=row["difficulty"],
            estimated_minutes=int(row["estimated_duration_minutes"]),
            mastery_target=float(row["mastery_target"]),
            target_score=int(row["target_score"]),
            language="uk",
        )
        fingerprint = self.engine.generation_identity(context, request)
        return replace(request, lesson_id=f"lesson-{fingerprint[:32]}"), context

    def _cached(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        request: LessonGenerationRequest,
        fingerprint: str,
    ) -> Lesson | None:
        lesson = self.repository.cached_lesson(
            connection,
            user_id=user_id,
            curriculum_id=request.curriculum_id,
            curriculum_unit_id=request.curriculum_unit_id,
            request_fingerprint=fingerprint,
        )
        if lesson is not None:
            validation = validate_lesson(lesson, request)
            if not validation.valid:
                raise CurriculumLessonPersistenceError(
                    "Stored lesson no longer satisfies the production contract."
                )
        return lesson

    def _record_generation_failure(
        self,
        *,
        user_id: int,
        request: LessonGenerationRequest,
        error_code: str,
    ) -> None:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self.repository.insert_event(
                connection,
                event_key=f"lesson-generation-failed:{uuid.uuid4()}",
                event_type="lesson_generation_failed",
                user_id=user_id,
                curriculum_id=request.curriculum_id,
                curriculum_unit_id=request.curriculum_unit_id,
                reason=error_code,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            self.logger.exception(
                "Lesson generation failure event could not be stored user_id=%s unit_id=%s",
                user_id,
                request.curriculum_unit_id,
            )
        finally:
            connection.close()

    def _load_or_generate(
        self,
        *,
        user_id: int,
        request: LessonGenerationRequest,
        context: AIContext,
    ) -> tuple[Lesson, bool]:
        fingerprint = self.engine.generation_identity(context, request)
        connection = self.repository.connect()
        try:
            cached = self._cached(
                connection,
                user_id=user_id,
                request=request,
                fingerprint=fingerprint,
            )
        finally:
            connection.close()
        if cached is not None:
            return cached, True

        with self._generation_lock(fingerprint):
            connection = self.repository.connect()
            try:
                cached = self._cached(
                    connection,
                    user_id=user_id,
                    request=request,
                    fingerprint=fingerprint,
                )
            finally:
                connection.close()
            if cached is not None:
                return cached, True

            result = self.engine.generate(context, request)
            if not result.success:
                code = result.error.code.value if result.error else "empty_result"
                self._record_generation_failure(
                    user_id=user_id,
                    request=request,
                    error_code=code,
                )
                raise CurriculumLessonGenerationUnavailable(
                    "The lesson could not be generated right now. Please try again later."
                )
            lesson = result.value
            connection = self.repository.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                progress = self.progress_service.get_active_unit_progress_in_transaction(
                    connection,
                    user_id=user_id,
                    curriculum_unit_id=request.curriculum_unit_id,
                    curriculum_id=request.curriculum_id,
                    subject=request.subject,
                )
                self._assert_readable_state(progress.state)
                lesson = self.repository.save_lesson(
                    connection,
                    user_id=user_id,
                    lesson=lesson,
                )
                self.repository.insert_event(
                    connection,
                    event_key=f"lesson-generated:{lesson.id}",
                    event_type="lesson_generated",
                    user_id=user_id,
                    curriculum_id=request.curriculum_id,
                    curriculum_unit_id=request.curriculum_unit_id,
                    lesson_id=lesson.id,
                    reason=f"validated_{lesson.generation_metadata.source}_generation",
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
            return lesson, False

    def deliver_lesson(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        subject: str,
    ) -> LessonDeliveryResult:
        try:
            return self._deliver_lesson(
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                subject=subject,
            )
        except sqlite3.Error as exc:
            self.logger.exception(
                "Lesson persistence failure user_id=%s unit_id=%s",
                user_id,
                curriculum_unit_id,
            )
            raise CurriculumLessonPersistenceError(
                "The lesson could not be loaded safely."
            ) from exc

    def _deliver_lesson(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        subject: str,
    ) -> LessonDeliveryResult:
        connection = self.repository.connect()
        try:
            request, context = self._request_and_context(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                subject=subject,
            )
        finally:
            connection.close()
        lesson, cached = self._load_or_generate(
            user_id=user_id,
            request=request,
            context=context,
        )

        connection = self.repository.connect()
        raw_token: str | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            progress = self.progress_service.get_active_unit_progress_in_transaction(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=request.curriculum_id,
                subject=subject,
            )
            self._assert_readable_state(progress.state)
            if progress.state is CurriculumUnitState.IN_PROGRESS:
                raw_token = secrets.token_urlsafe(32)
                delivery_id = f"delivery-{uuid.uuid4()}"
                evidence_id = f"lesson-evidence-{uuid.uuid4()}"
                self.repository.create_delivery(
                    connection,
                    delivery_id=delivery_id,
                    completion_token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                    evidence_id=evidence_id,
                    user_id=user_id,
                    lesson=lesson,
                )
                self.repository.insert_event(
                    connection,
                    event_key=f"lesson-delivered:{delivery_id}",
                    event_type="lesson_delivered",
                    user_id=user_id,
                    curriculum_id=request.curriculum_id,
                    curriculum_unit_id=curriculum_unit_id,
                    lesson_id=lesson.id,
                    reason="authenticated_delivery",
                )
            elif cached:
                self.repository.insert_event(
                    connection,
                    event_key=f"lesson-cache-hit:{uuid.uuid4()}",
                    event_type="lesson_cache_hit",
                    user_id=user_id,
                    curriculum_id=request.curriculum_id,
                    curriculum_unit_id=curriculum_unit_id,
                    lesson_id=lesson.id,
                    reason="post_lesson_revisit",
                )
            connection.commit()
            return LessonDeliveryResult(
                lesson=lesson,
                progress=progress,
                delivery_token=raw_token,
                cached=cached,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete_lesson(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        subject: str,
        delivery_token: str,
    ) -> LessonCompletionResult:
        try:
            return self._complete_lesson(
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                subject=subject,
                delivery_token=delivery_token,
            )
        except sqlite3.Error as exc:
            self.logger.exception(
                "Lesson completion persistence failure user_id=%s unit_id=%s",
                user_id,
                curriculum_unit_id,
            )
            raise CurriculumLessonPersistenceError(
                "Lesson completion could not be saved safely."
            ) from exc

    def _complete_lesson(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        subject: str,
        delivery_token: str,
    ) -> LessonCompletionResult:
        if not isinstance(delivery_token, str):
            raise CurriculumLessonDeliveryInvalid("Lesson delivery token is required.")
        token = delivery_token.strip()
        if not 40 <= len(token) <= 200:
            raise CurriculumLessonDeliveryInvalid("Lesson delivery token is invalid.")
        token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            delivery = self.repository.delivery_row(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                completion_token_hash=token_digest,
            )
            if delivery["curriculum_status"] != "published" or delivery["subject"] != subject:
                raise CurriculumLessonNotAvailable("Lesson delivery is no longer active.")
            try:
                stored_payload = json.loads(delivery["content_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise CurriculumLessonPersistenceError(
                    "Stored lesson content is invalid."
                ) from exc
            stored_hash = content_hash(stored_payload)
            if (
                stored_hash != delivery["content_hash"]
                or stored_hash != delivery["lesson_content_hash"]
                or delivery["curriculum_id"] != delivery["lesson_curriculum_id"]
                or delivery["curriculum_unit_id"]
                != delivery["lesson_curriculum_unit_id"]
            ):
                raise CurriculumLessonConflict("Lesson content changed after delivery.")

            progress = self.progress_service.get_active_unit_progress_in_transaction(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=delivery["curriculum_id"],
                subject=subject,
            )
            if delivery["completed_at"] is not None:
                connection.commit()
                return LessonCompletionResult(
                    progress=progress,
                    evidence_id=delivery["evidence_id"],
                    completed_at=delivery["completed_at"],
                    idempotent=True,
                )

            verified_at = datetime.now(timezone.utc).replace(microsecond=0)
            evidence = LessonCompletionEvidence(
                evidence_id=delivery["evidence_id"],
                verified_at=verified_at,
                source=LessonCompletionSource.SERVER_LESSON,
            )
            progress = self.progress_service.complete_lesson_for_assessment_in_transaction(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=delivery["curriculum_id"],
                subject=subject,
                completion_evidence=evidence,
            )
            completed_at = verified_at.isoformat(timespec="seconds")
            if not self.repository.complete_delivery(
                connection,
                delivery_id=delivery["id"],
                completed_at=completed_at,
            ):
                raise CurriculumLessonConflict("Lesson delivery was completed concurrently.")
            self.repository.insert_event(
                connection,
                event_key=f"lesson-completion:{delivery['id']}",
                event_type="lesson_completion_accepted",
                user_id=user_id,
                curriculum_id=delivery["curriculum_id"],
                curriculum_unit_id=curriculum_unit_id,
                lesson_id=delivery["lesson_id"],
                reason="server_delivery_evidence_verified",
                created_at=completed_at,
            )
            connection.commit()
            return LessonCompletionResult(
                progress=progress,
                evidence_id=delivery["evidence_id"],
                completed_at=completed_at,
                idempotent=False,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
