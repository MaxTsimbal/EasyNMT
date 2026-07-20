"""Transactional curriculum progress, unlocking, mastery, and XP service."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Optional, Sequence

from easynmt_ai.curriculum.taxonomy import (
    LEGACY_MATH_LESSON_TOPIC_MAP,
    MathTaxonomy,
    load_math_taxonomy,
)

from .errors import (
    AssessmentEvidenceInvalid,
    CurriculumNotActive,
    CurriculumProgressNotFound,
    CurriculumSuperseded,
    CurriculumUnitNotFound,
    InvalidProgressTransition,
    PrerequisitesNotSatisfied,
    ProgressConflict,
    ProgressInitializationError,
)
from .models import (
    AssessmentSource,
    CheckpointState,
    CurriculumCheckpointProgressView,
    CurriculumProgressSnapshot,
    CurriculumUnitProgress,
    CurriculumUnitProgressView,
    CurriculumUnitState,
    LessonCompletionEvidence,
    LessonCompletionSource,
    MasteryBand,
    ReviewReason,
    ServerVerifiedAssessmentResult,
    UnlockRecalculationResult,
)
from .policy import (
    CURRICULUM_UNIT_COMPLETION_XP,
    mastery_after_assessment,
    next_allowed_action,
    require_transition,
)
from .repository import CurriculumProgressRepository, utc_now


ACTIVE_WORK_STATES = frozenset({
    CurriculumUnitState.IN_PROGRESS,
    CurriculumUnitState.LESSON_COMPLETED,
    CurriculumUnitState.ASSESSMENT_REQUIRED,
})


class CurriculumProgressService:
    """The only application boundary permitted to mutate curriculum progress."""

    def __init__(
        self,
        repository: CurriculumProgressRepository,
        *,
        taxonomy: Optional[MathTaxonomy] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.repository = repository
        self.taxonomy = taxonomy or load_math_taxonomy()
        self.logger = logger or logging.getLogger("easynmt.curriculum_progress")

    @staticmethod
    def _stable_id(prefix: str, *parts: object) -> str:
        source = "|".join(str(part) for part in parts)
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:28]
        return f"{prefix}-{digest}"

    @staticmethod
    def _assert_active(curriculum_row: sqlite3.Row) -> None:
        status = (
            curriculum_row["status"]
            if "status" in curriculum_row.keys()
            else curriculum_row["curriculum_status"]
        )
        if status == "superseded":
            raise CurriculumSuperseded("Superseded curricula cannot receive progress updates.")
        if status != "published":
            raise CurriculumNotActive("Curriculum is not the active published curriculum.")

    @staticmethod
    def _check_expected_version(row: sqlite3.Row, expected_version: Optional[int]) -> None:
        if expected_version is None:
            return
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
        ):
            raise ProgressConflict("Expected progress version is invalid.")
        if int(row["version"]) != expected_version:
            raise ProgressConflict("Curriculum progress changed since it was read.")

    def _transition(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        target: CurriculumUnitState,
        *,
        now: str,
        assignments: Optional[dict[str, object]] = None,
    ) -> sqlite3.Row:
        previous = CurriculumUnitState(row["state"])
        require_transition(previous, target)
        values = dict(assignments or {})
        values.update({
            "state": target.value,
            "last_activity_at": now,
            "updated_at": now,
        })
        allowed_columns = {
            "state",
            "mastery_score",
            "mastery_band",
            "attempt_count",
            "xp_awarded",
            "lesson_started_at",
            "lesson_completed_at",
            "assessment_required_at",
            "completed_at",
            "review_required_at",
            "last_activity_at",
            "updated_at",
            "source",
        }
        if set(values) - allowed_columns:
            raise ValueError("Unsupported curriculum progress update")
        setters = ", ".join(f"{column} = ?" for column in values)
        parameters = [*values.values(), row["id"], int(row["version"]), previous.value]
        cursor = connection.execute(
            f"""
            UPDATE curriculum_unit_progress
            SET {setters}, version = version + 1
            WHERE id = ? AND version = ? AND state = ?
            """,
            parameters,
        )
        if cursor.rowcount != 1:
            raise ProgressConflict("Curriculum progress was updated concurrently.")
        return connection.execute(
            "SELECT * FROM curriculum_unit_progress WHERE id = ?",
            (row["id"],),
        ).fetchone()

    def _credit_candidates(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_row: sqlite3.Row,
        previous_curriculum_ids: Sequence[str],
    ) -> dict[str, tuple[str, str, float]]:
        credits: dict[str, tuple[str, str, float]] = {}
        try:
            metadata = json.loads(curriculum_row["generation_metadata_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        for topic_id in metadata.get("mastered_topic_ids", ()):
            if topic_id in self.taxonomy.topics_by_id:
                credits[str(topic_id)] = (
                    "generation_mastery_snapshot",
                    curriculum_row["context_fingerprint"],
                    0.75,
                )

        if curriculum_row["subject"] == "math":
            legacy_rows = connection.execute(
                """
                SELECT lesson_id, best_score, total
                FROM completed_lessons
                WHERE user_id = ? AND subject = 'math'
                """,
                (int(user_id),),
            ).fetchall()
            for legacy in legacy_rows:
                topic_id = LEGACY_MATH_LESSON_TOPIC_MAP.get(int(legacy["lesson_id"]))
                if topic_id:
                    ratio = (
                        float(legacy["best_score"]) / float(legacy["total"])
                        if float(legacy["total"] or 0) > 0
                        else 0.75
                    )
                    credits[topic_id] = (
                        "legacy_completion",
                        f"legacy-lesson-{legacy['lesson_id']}",
                        max(0.65, min(0.85, ratio)),
                    )

        prior_ids = tuple(str(item) for item in previous_curriculum_ids if item)
        if not prior_ids:
            prior_rows = connection.execute(
                """
                SELECT id FROM ai_curricula
                WHERE user_id = ? AND subject = ? AND status = 'superseded'
                """,
                (int(user_id), curriculum_row["subject"]),
            ).fetchall()
            prior_ids = tuple(row["id"] for row in prior_rows)
        if prior_ids:
            placeholders = ",".join("?" for _ in prior_ids)
            rows = connection.execute(
                f"""
                SELECT topic_id, curriculum_id, mastery_score
                FROM curriculum_unit_progress
                WHERE user_id = ? AND curriculum_id IN ({placeholders})
                  AND state = 'completed'
                ORDER BY updated_at
                """,
                (int(user_id), *prior_ids),
            ).fetchall()
            for prior in rows:
                score = max(0.65, min(1.0, float(prior["mastery_score"] or 0.75)))
                credits[prior["topic_id"]] = (
                    "prior_curriculum",
                    prior["curriculum_id"],
                    score,
                )
        return credits

    @staticmethod
    def _progress_source(credit_source: str) -> str:
        return {
            "legacy_completion": "legacy_credit",
            "prior_curriculum": "prior_curriculum_credit",
            "generation_mastery_snapshot": "generation_mastery_credit",
        }[credit_source]

    def _initialize_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_id: str,
        previous_curriculum_ids: Sequence[str] = (),
    ) -> None:
        curriculum = self.repository.curriculum_row(
            connection,
            user_id=user_id,
            curriculum_id=curriculum_id,
        )
        self._assert_active(curriculum)
        units = connection.execute(
            """
            SELECT * FROM ai_curriculum_units
            WHERE curriculum_id = ? ORDER BY position
            """,
            (curriculum_id,),
        ).fetchall()
        if not units:
            raise ProgressInitializationError("Published curriculum has no units.")
        checkpoints = connection.execute(
            """
            SELECT * FROM ai_curriculum_checkpoints
            WHERE curriculum_id = ? ORDER BY position
            """,
            (curriculum_id,),
        ).fetchall()
        existing_units = int(connection.execute(
            """
            SELECT COUNT(*) FROM curriculum_unit_progress
            WHERE user_id = ? AND curriculum_id = ?
            """,
            (int(user_id), curriculum_id),
        ).fetchone()[0])
        existing_checkpoints = int(connection.execute(
            """
            SELECT COUNT(*) FROM curriculum_checkpoint_progress
            WHERE user_id = ? AND curriculum_id = ?
            """,
            (int(user_id), curriculum_id),
        ).fetchone()[0])
        fully_missing = existing_units == 0 and existing_checkpoints == 0
        fully_initialized = (
            existing_units == len(units)
            and existing_checkpoints == len(checkpoints)
        )
        if not fully_missing and not fully_initialized:
            raise ProgressInitializationError(
                "Curriculum progress is only partially initialized."
            )

        now = utc_now()
        if existing_units == 0:
            credits = self._credit_candidates(
                connection,
                user_id=user_id,
                curriculum_row=curriculum,
                previous_curriculum_ids=previous_curriculum_ids,
            )
            for topic_id, (source, reference, score) in credits.items():
                connection.execute(
                    """
                    INSERT INTO curriculum_topic_credits (
                        user_id, curriculum_id, topic_id, source,
                        source_reference, mastery_score, credited_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, curriculum_id, topic_id) DO NOTHING
                    """,
                    (int(user_id), curriculum_id, topic_id, source, reference, score, now),
                )

            for unit in units:
                credit = credits.get(unit["topic_id"])
                state = CurriculumUnitState.LOCKED
                mastery_score = None
                mastery_band = MasteryBand.UNKNOWN
                completed_at = None
                review_required_at = None
                source = "curriculum"
                if credit and unit["reason_code"] == "review_mastered":
                    state = CurriculumUnitState.REVIEW_REQUIRED
                    mastery_score = credit[2]
                    mastery_band = MasteryBand.NEEDS_REVIEW
                    review_required_at = now
                    source = self._progress_source(credit[0])
                elif credit:
                    state = CurriculumUnitState.COMPLETED
                    mastery_score = credit[2]
                    mastery_band = (
                        MasteryBand.MASTERED if credit[2] >= 0.9 else MasteryBand.PROFICIENT
                    )
                    completed_at = now
                    source = self._progress_source(credit[0])
                progress_id = self._stable_id(
                    "cup",
                    user_id,
                    curriculum_id,
                    unit["unit_id"],
                )
                connection.execute(
                    """
                    INSERT INTO curriculum_unit_progress (
                        id, user_id, curriculum_id, curriculum_unit_id, topic_id,
                        state, mastery_score, mastery_band, attempt_count, xp_awarded,
                        completed_at, review_required_at, last_activity_at, source,
                        version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        progress_id,
                        int(user_id),
                        curriculum_id,
                        unit["unit_id"],
                        unit["topic_id"],
                        state.value,
                        mastery_score,
                        mastery_band.value,
                        completed_at,
                        review_required_at,
                        now,
                        source,
                        now,
                        now,
                    ),
                )
                if credit:
                    self.repository.insert_event(
                        connection,
                        event_key=f"migration:{curriculum_id}:{unit['topic_id']}:{credit[0]}",
                        event_type="curriculum_progress_migrated",
                        user_id=user_id,
                        curriculum_id=curriculum_id,
                        curriculum_unit_id=unit["unit_id"],
                        topic_id=unit["topic_id"],
                        previous_state=None,
                        new_state=state.value,
                        reason=credit[0],
                        idempotency_key=credit[1],
                        metadata={"mastery_score": credit[2]},
                        created_at=now,
                    )

            for checkpoint in checkpoints:
                connection.execute(
                    """
                    INSERT INTO curriculum_checkpoint_progress (
                        id, user_id, curriculum_id, checkpoint_id, state,
                        attempt_count, last_activity_at, version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'locked', 0, ?, 1, ?, ?)
                    """,
                    (
                        self._stable_id(
                            "ccp",
                            user_id,
                            curriculum_id,
                            checkpoint["checkpoint_id"],
                        ),
                        int(user_id),
                        curriculum_id,
                        checkpoint["checkpoint_id"],
                        now,
                        now,
                        now,
                    ),
                )
            self.repository.insert_event(
                connection,
                event_key=f"initialize:{curriculum_id}",
                event_type="curriculum_progress_initialized",
                user_id=user_id,
                curriculum_id=curriculum_id,
                reason="curriculum_published",
                idempotency_key=curriculum_id,
                metadata={
                    "unit_count": len(units),
                    "checkpoint_count": len(checkpoints),
                    "credit_count": len(credits),
                },
                created_at=now,
            )
        elif existing_checkpoints == 0 and checkpoints:
            raise ProgressInitializationError(
                "Curriculum checkpoints are missing from initialized progress."
            )
        self._recalculate_in_transaction(
            connection,
            user_id=user_id,
            curriculum_id=curriculum_id,
        )

    def initialize_for_publication(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_id: str,
        previous_curriculum_ids: Sequence[str],
    ) -> None:
        """Publication hook. The caller owns the surrounding transaction."""

        self._initialize_in_transaction(
            connection,
            user_id=user_id,
            curriculum_id=curriculum_id,
            previous_curriculum_ids=previous_curriculum_ids,
        )

    def initialize_curriculum_progress(
        self,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> CurriculumProgressSnapshot:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._initialize_in_transaction(
                connection,
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_curriculum_progress(
            user_id=user_id,
            curriculum_id=curriculum_id,
        )

    def _recalculate_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> UnlockRecalculationResult:
        curriculum = self.repository.curriculum_row(
            connection,
            user_id=user_id,
            curriculum_id=curriculum_id,
        )
        self._assert_active(curriculum)
        now = utc_now()
        progress_rows = connection.execute(
            """
            SELECT p.*, u.position, u.prerequisite_topic_ids_json
            FROM curriculum_unit_progress p
            JOIN ai_curriculum_units u
              ON u.curriculum_id = p.curriculum_id AND u.unit_id = p.curriculum_unit_id
            WHERE p.user_id = ? AND p.curriculum_id = ?
            ORDER BY u.position
            """,
            (int(user_id), curriculum_id),
        ).fetchall()
        if not progress_rows:
            raise CurriculumProgressNotFound("Curriculum progress is not initialized.")
        credit_rows = connection.execute(
                """
                SELECT topic_id FROM curriculum_topic_credits
                WHERE user_id = ? AND curriculum_id = ?
                """,
                (int(user_id), curriculum_id),
            ).fetchall()
        current_states_by_topic = {
            row["topic_id"]: row["state"] for row in progress_rows
        }
        credited_topics = {
            row["topic_id"]
            for row in credit_rows
            if row["topic_id"] not in current_states_by_topic
            or current_states_by_topic[row["topic_id"]]
            == CurriculumUnitState.COMPLETED.value
        }
        completed_topics = credited_topics | {
            row["topic_id"]
            for row in progress_rows
            if row["state"] == CurriculumUnitState.COMPLETED.value
        }

        checkpoint_rows = connection.execute(
            """
            SELECT p.*, c.after_unit_order, c.topic_ids_json
            FROM curriculum_checkpoint_progress p
            JOIN ai_curriculum_checkpoints c
              ON c.curriculum_id = p.curriculum_id AND c.checkpoint_id = p.checkpoint_id
            WHERE p.user_id = ? AND p.curriculum_id = ?
            ORDER BY c.position
            """,
            (int(user_id), curriculum_id),
        ).fetchall()
        newly_available_checkpoints: list[str] = []
        for checkpoint in checkpoint_rows:
            if checkpoint["state"] != CheckpointState.LOCKED.value:
                continue
            topic_ids = set(json.loads(checkpoint["topic_ids_json"] or "[]"))
            if topic_ids and topic_ids <= completed_topics:
                cursor = connection.execute(
                    """
                    UPDATE curriculum_checkpoint_progress
                    SET state = 'available', available_at = ?, last_activity_at = ?,
                        updated_at = ?, version = version + 1
                    WHERE id = ? AND state = 'locked' AND version = ?
                    """,
                    (now, now, now, checkpoint["id"], int(checkpoint["version"])),
                )
                if cursor.rowcount != 1:
                    raise ProgressConflict("Checkpoint progress changed concurrently.")
                newly_available_checkpoints.append(checkpoint["checkpoint_id"])
                self.repository.insert_event(
                    connection,
                    event_key=f"checkpoint-available:{curriculum_id}:{checkpoint['checkpoint_id']}",
                    event_type="curriculum_checkpoint_available",
                    user_id=user_id,
                    curriculum_id=curriculum_id,
                    checkpoint_id=checkpoint["checkpoint_id"],
                    previous_state=CheckpointState.LOCKED.value,
                    new_state=CheckpointState.AVAILABLE.value,
                    reason="checkpoint_topics_completed",
                    created_at=now,
                )

        current_checkpoints = connection.execute(
            """
            SELECT p.state, c.after_unit_order
            FROM curriculum_checkpoint_progress p
            JOIN ai_curriculum_checkpoints c
              ON c.curriculum_id = p.curriculum_id AND c.checkpoint_id = p.checkpoint_id
            WHERE p.user_id = ? AND p.curriculum_id = ?
            """,
            (int(user_id), curriculum_id),
        ).fetchall()
        newly_available_units: list[str] = []
        for row in progress_rows:
            if row["state"] != CurriculumUnitState.LOCKED.value:
                continue
            direct = tuple(json.loads(row["prerequisite_topic_ids_json"] or "[]"))
            try:
                closure = self.taxonomy.prerequisite_closure(direct) if direct else set()
            except KeyError as exc:
                raise ProgressInitializationError(
                    "Curriculum contains an unknown prerequisite topic."
                ) from exc
            checkpoint_blocked = any(
                int(checkpoint["after_unit_order"]) < int(row["position"])
                and checkpoint["state"] != CheckpointState.COMPLETED.value
                for checkpoint in current_checkpoints
            )
            if closure <= completed_topics and not checkpoint_blocked:
                transitioned = self._transition(
                    connection,
                    row,
                    CurriculumUnitState.AVAILABLE,
                    now=now,
                )
                newly_available_units.append(row["curriculum_unit_id"])
                self.repository.insert_event(
                    connection,
                    event_key=f"available:{curriculum_id}:{row['curriculum_unit_id']}",
                    event_type="curriculum_unit_available",
                    user_id=user_id,
                    curriculum_id=curriculum_id,
                    curriculum_unit_id=row["curriculum_unit_id"],
                    topic_id=row["topic_id"],
                    previous_state=row["state"],
                    new_state=transitioned["state"],
                    reason="prerequisites_and_checkpoints_satisfied",
                    created_at=now,
                )
        changed = tuple(sorted((*newly_available_units, *newly_available_checkpoints)))
        if changed:
            digest = hashlib.sha256("|".join(changed).encode("utf-8")).hexdigest()[:20]
            self.repository.insert_event(
                connection,
                event_key=f"recalculate:{curriculum_id}:{digest}",
                event_type="curriculum_unlocks_recalculated",
                user_id=user_id,
                curriculum_id=curriculum_id,
                reason="deterministic_unlock_policy",
                metadata={
                    "unit_ids": newly_available_units,
                    "checkpoint_ids": newly_available_checkpoints,
                },
                created_at=now,
            )
        return UnlockRecalculationResult(
            curriculum_id=curriculum_id,
            newly_available_unit_ids=tuple(newly_available_units),
            newly_available_checkpoint_ids=tuple(newly_available_checkpoints),
            unchanged=not changed,
        )

    def recalculate_unlocks(
        self,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> UnlockRecalculationResult:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = self._recalculate_in_transaction(
                connection,
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _unit_for_update(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_unit_id: str,
        curriculum_id: Optional[str],
        expected_version: Optional[int],
        subject: Optional[str] = None,
        check_expected_version: bool = True,
    ) -> sqlite3.Row:
        row = self.repository.unit_progress_row(
            connection,
            user_id=user_id,
            curriculum_unit_id=curriculum_unit_id,
            curriculum_id=curriculum_id,
        )
        self._assert_active(row)
        if subject is not None and row["subject"] != str(subject):
            raise CurriculumUnitNotFound("Curriculum unit is not in the active subject.")
        if check_expected_version:
            self._check_expected_version(row, expected_version)
        return row

    def start_curriculum_unit(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        curriculum_id: Optional[str] = None,
        expected_version: Optional[int] = None,
        subject: Optional[str] = None,
    ) -> CurriculumUnitProgress:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._unit_for_update(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
                expected_version=expected_version,
                subject=subject,
                check_expected_version=False,
            )
            current = CurriculumUnitState(row["state"])
            if current is CurriculumUnitState.IN_PROGRESS:
                connection.commit()
                return self.repository.progress_from_row(row)
            self._check_expected_version(row, expected_version)
            if current is CurriculumUnitState.LOCKED:
                raise PrerequisitesNotSatisfied("Unit prerequisites are not satisfied.")
            if current not in {
                CurriculumUnitState.AVAILABLE,
                CurriculumUnitState.REVIEW_REQUIRED,
            }:
                raise InvalidProgressTransition("This curriculum unit cannot be started now.")
            now = utc_now()
            transitioned = self._transition(
                connection,
                row,
                CurriculumUnitState.IN_PROGRESS,
                now=now,
                assignments={"lesson_started_at": row["lesson_started_at"] or now},
            )
            self.repository.insert_event(
                connection,
                event_key=f"start:{row['curriculum_id']}:{row['curriculum_unit_id']}:{row['version']}",
                event_type="curriculum_unit_started",
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
                topic_id=row["topic_id"],
                previous_state=current.value,
                new_state=CurriculumUnitState.IN_PROGRESS.value,
                reason=("review_started" if current is CurriculumUnitState.REVIEW_REQUIRED else "lesson_started"),
                created_at=now,
            )
            connection.commit()
            return self.repository.progress_from_row(transitioned)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_active_unit_progress_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_unit_id: str,
        curriculum_id: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> CurriculumUnitProgress:
        """Read an active owner-scoped unit inside a caller-owned transaction."""

        row = self._unit_for_update(
            connection,
            user_id=user_id,
            curriculum_unit_id=curriculum_unit_id,
            curriculum_id=curriculum_id,
            expected_version=None,
            subject=subject,
        )
        return self.repository.progress_from_row(row)

    def _mark_lesson_completed_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        user_id: int,
        completion_evidence: LessonCompletionEvidence,
        expected_version: Optional[int],
    ) -> sqlite3.Row:
        event_key = (
            f"lesson-completed:{row['curriculum_id']}:"
            f"{row['curriculum_unit_id']}:{completion_evidence.evidence_id}"
        )
        existing_event = connection.execute(
            """
            SELECT reason, idempotency_key, created_at
            FROM curriculum_progress_events WHERE event_key = ?
            """,
            (event_key,),
        ).fetchone()
        if existing_event:
            if (
                existing_event["reason"] != completion_evidence.source.value
                or existing_event["idempotency_key"]
                != completion_evidence.evidence_id
                or existing_event["created_at"]
                != completion_evidence.verified_at.isoformat(timespec="seconds")
            ):
                raise InvalidProgressTransition(
                    "Lesson evidence ID was reused with different evidence."
                )
            return connection.execute(
                "SELECT * FROM curriculum_unit_progress WHERE id = ?",
                (row["id"],),
            ).fetchone()
        self._check_expected_version(row, expected_version)
        if CurriculumUnitState(row["state"]) is not CurriculumUnitState.IN_PROGRESS:
            raise InvalidProgressTransition("Only an in-progress lesson can be completed.")
        if completion_evidence.source is LessonCompletionSource.LEGACY_LESSON:
            expected_topic = LEGACY_MATH_LESSON_TOPIC_MAP.get(
                int(completion_evidence.legacy_lesson_id)
            )
            legacy_completion = connection.execute(
                """
                SELECT 1 FROM completed_lessons
                WHERE user_id = ? AND subject = ? AND lesson_id = ?
                """,
                (
                    int(user_id),
                    row["subject"],
                    int(completion_evidence.legacy_lesson_id),
                ),
            ).fetchone()
            if expected_topic != row["topic_id"] or legacy_completion is None:
                raise InvalidProgressTransition(
                    "Legacy lesson evidence does not match this curriculum topic."
                )
        now = completion_evidence.verified_at.isoformat(timespec="seconds")
        transitioned = self._transition(
            connection,
            row,
            CurriculumUnitState.LESSON_COMPLETED,
            now=now,
            assignments={
                "lesson_completed_at": now,
                "mastery_band": MasteryBand.INTRODUCED.value,
            },
        )
        self.repository.insert_event(
            connection,
            event_key=event_key,
            event_type="curriculum_unit_lesson_completed",
            user_id=user_id,
            curriculum_id=row["curriculum_id"],
            curriculum_unit_id=row["curriculum_unit_id"],
            topic_id=row["topic_id"],
            previous_state=row["state"],
            new_state=transitioned["state"],
            reason=completion_evidence.source.value,
            idempotency_key=completion_evidence.evidence_id,
            metadata={"legacy_lesson_id": completion_evidence.legacy_lesson_id},
            created_at=now,
        )
        return transitioned

    def mark_lesson_completed(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        completion_evidence: LessonCompletionEvidence,
        curriculum_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> CurriculumUnitProgress:
        if not isinstance(completion_evidence, LessonCompletionEvidence):
            raise InvalidProgressTransition("Typed lesson completion evidence is required.")
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._unit_for_update(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
                expected_version=expected_version,
                check_expected_version=False,
            )
            transitioned = self._mark_lesson_completed_in_transaction(
                connection,
                row=row,
                user_id=user_id,
                completion_evidence=completion_evidence,
                expected_version=expected_version,
            )
            connection.commit()
            return self.repository.progress_from_row(transitioned)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _mark_assessment_required_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        user_id: int,
        expected_version: Optional[int],
        now: Optional[str] = None,
    ) -> sqlite3.Row:
        current = CurriculumUnitState(row["state"])
        if current is CurriculumUnitState.ASSESSMENT_REQUIRED:
            return row
        self._check_expected_version(row, expected_version)
        if current is not CurriculumUnitState.LESSON_COMPLETED:
            raise InvalidProgressTransition(
                "Assessment can only follow a completed lesson."
            )
        transition_time = now or utc_now()
        transitioned = self._transition(
            connection,
            row,
            CurriculumUnitState.ASSESSMENT_REQUIRED,
            now=transition_time,
            assignments={"assessment_required_at": transition_time},
        )
        self.repository.insert_event(
            connection,
            event_key=(
                f"assessment-required:{row['curriculum_id']}:"
                f"{row['curriculum_unit_id']}:{row['version']}"
            ),
            event_type="curriculum_unit_assessment_required",
            user_id=user_id,
            curriculum_id=row["curriculum_id"],
            curriculum_unit_id=row["curriculum_unit_id"],
            topic_id=row["topic_id"],
            previous_state=current.value,
            new_state=transitioned["state"],
            reason="lesson_completion_verified",
            created_at=transition_time,
        )
        return transitioned

    def mark_assessment_required(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        curriculum_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> CurriculumUnitProgress:
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._unit_for_update(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
                expected_version=expected_version,
                check_expected_version=False,
            )
            transitioned = self._mark_assessment_required_in_transaction(
                connection,
                row=row,
                user_id=user_id,
                expected_version=expected_version,
            )
            connection.commit()
            return self.repository.progress_from_row(transitioned)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete_lesson_for_assessment_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_unit_id: str,
        completion_evidence: LessonCompletionEvidence,
        curriculum_id: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> CurriculumUnitProgress:
        """Apply trusted lesson evidence and require assessment atomically.

        The caller owns the transaction. This is the production Lesson Engine
        integration boundary; progress transitions still occur only here.
        """

        if not isinstance(completion_evidence, LessonCompletionEvidence):
            raise InvalidProgressTransition("Typed lesson completion evidence is required.")
        row = self._unit_for_update(
            connection,
            user_id=user_id,
            curriculum_unit_id=curriculum_unit_id,
            curriculum_id=curriculum_id,
            expected_version=None,
            subject=subject,
            check_expected_version=False,
        )
        state = CurriculumUnitState(row["state"])
        if state is CurriculumUnitState.IN_PROGRESS:
            row = self._mark_lesson_completed_in_transaction(
                connection,
                row=row,
                user_id=user_id,
                completion_evidence=completion_evidence,
                expected_version=None,
            )
            state = CurriculumUnitState(row["state"])
        if state is CurriculumUnitState.LESSON_COMPLETED:
            row = self._mark_assessment_required_in_transaction(
                connection,
                row=row,
                user_id=user_id,
                expected_version=None,
                now=completion_evidence.verified_at.isoformat(timespec="seconds"),
            )
            state = CurriculumUnitState(row["state"])
        if state not in {
            CurriculumUnitState.ASSESSMENT_REQUIRED,
            CurriculumUnitState.COMPLETED,
        }:
            raise InvalidProgressTransition(
                "Lesson completion is not allowed from the current unit state."
            )
        return self.repository.progress_from_row(row)

    def _existing_assessment(
        self,
        connection: sqlite3.Connection,
        *,
        result: ServerVerifiedAssessmentResult,
        user_id: int,
        curriculum_id: str,
        curriculum_unit_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
    ) -> bool:
        existing = connection.execute(
            "SELECT * FROM curriculum_assessment_results WHERE attempt_id = ?",
            (result.attempt_id,),
        ).fetchone()
        if existing is None:
            return False
        if (
            int(existing["user_id"]) != int(user_id)
            or existing["curriculum_id"] != curriculum_id
            or existing["curriculum_unit_id"] != curriculum_unit_id
            or existing["checkpoint_id"] != checkpoint_id
        ):
            raise AssessmentEvidenceInvalid(
                "Assessment attempt ID was already used for another target."
            )
        expected_verified_at = result.verified_at.isoformat(timespec="seconds")
        if (
            bool(existing["passed"]) is not result.passed
            or float(existing["score"]) != result.score
            or float(existing["max_score"]) != result.max_score
            or existing["source"] != result.source.value
            or existing["verified_at"] != expected_verified_at
        ):
            raise AssessmentEvidenceInvalid(
                "Assessment attempt ID was reused with different evidence."
            )
        return True

    def _insert_assessment(
        self,
        connection: sqlite3.Connection,
        *,
        result: ServerVerifiedAssessmentResult,
        user_id: int,
        curriculum_id: str,
        curriculum_unit_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        topic_id: Optional[str] = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO curriculum_assessment_results (
                attempt_id, user_id, curriculum_id, curriculum_unit_id,
                checkpoint_id, topic_id, passed, score, max_score,
                normalized_score, source, verified_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.attempt_id,
                int(user_id),
                curriculum_id,
                curriculum_unit_id,
                checkpoint_id,
                topic_id,
                int(result.passed),
                result.score,
                result.max_score,
                result.normalized_score,
                result.source.value,
                result.verified_at.isoformat(timespec="seconds"),
                utc_now(),
            ),
        )

    @staticmethod
    def _award_xp(
        connection: sqlite3.Connection,
        *,
        user_id: int,
        subject: str,
        amount: int,
    ) -> None:
        if amount <= 0:
            return
        connection.execute(
            """
            INSERT INTO user_subject_progress (user_id, subject, xp)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, subject) DO UPDATE SET
                xp = user_subject_progress.xp + excluded.xp,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(user_id), subject, int(amount)),
        )
        connection.execute(
            """
            UPDATE user_plans
            SET xp = xp + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND subject = ?
            """,
            (int(amount), int(user_id), subject),
        )

    def record_assessment_result(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        result: ServerVerifiedAssessmentResult,
        curriculum_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> CurriculumUnitProgress:
        if not isinstance(result, ServerVerifiedAssessmentResult):
            raise AssessmentEvidenceInvalid("Typed server assessment evidence is required.")
        if result.source in {
            AssessmentSource.CHECKPOINT_ASSESSMENT,
            AssessmentSource.SERVER_REVIEW,
        }:
            raise AssessmentEvidenceInvalid("Assessment source does not match a normal unit.")
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._unit_for_update(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
                expected_version=expected_version,
                check_expected_version=False,
            )
            if self._existing_assessment(
                connection,
                result=result,
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
            ):
                connection.commit()
                return self.repository.progress_from_row(row)
            self._check_expected_version(row, expected_version)
            if CurriculumUnitState(row["state"]) is not CurriculumUnitState.ASSESSMENT_REQUIRED:
                raise InvalidProgressTransition(
                    "Unit is not waiting for an assessment result."
                )
            self._insert_assessment(
                connection,
                result=result,
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
                topic_id=row["topic_id"],
            )
            if result.source is AssessmentSource.LEGACY_QUIZ:
                legacy_lesson_ids = tuple(
                    lesson_id
                    for lesson_id, topic_id in LEGACY_MATH_LESSON_TOPIC_MAP.items()
                    if topic_id == row["topic_id"]
                )
                if not legacy_lesson_ids:
                    raise AssessmentEvidenceInvalid(
                        "Legacy quiz evidence does not map to this curriculum topic."
                    )
                placeholders = ",".join("?" for _ in legacy_lesson_ids)
                legacy_completion = connection.execute(
                    f"""
                    SELECT 1 FROM completed_lessons
                    WHERE user_id = ? AND subject = ?
                      AND lesson_id IN ({placeholders})
                    """,
                    (int(user_id), row["subject"], *legacy_lesson_ids),
                ).fetchone()
                if legacy_completion is None:
                    raise AssessmentEvidenceInvalid(
                        "Legacy quiz evidence has no matching stored completion."
                    )
            mastery_score, mastery_band = mastery_after_assessment(
                previous_score=row["mastery_score"],
                normalized_score=result.normalized_score,
                passed=result.passed,
            )
            now = result.verified_at.isoformat(timespec="seconds")
            attempt_count = int(row["attempt_count"]) + 1
            if not result.passed:
                cursor = connection.execute(
                    """
                    UPDATE curriculum_unit_progress
                    SET mastery_score = ?, mastery_band = ?, attempt_count = ?,
                        last_activity_at = ?, updated_at = ?, version = version + 1
                    WHERE id = ? AND state = 'assessment_required' AND version = ?
                    """,
                    (
                        mastery_score,
                        mastery_band.value,
                        attempt_count,
                        now,
                        now,
                        row["id"],
                        int(row["version"]),
                    ),
                )
                if cursor.rowcount != 1:
                    raise ProgressConflict("Assessment progress changed concurrently.")
                updated = connection.execute(
                    "SELECT * FROM curriculum_unit_progress WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                self.repository.insert_event(
                    connection,
                    event_key=f"assessment-failed:{result.attempt_id}",
                    event_type="curriculum_unit_assessment_failed",
                    user_id=user_id,
                    curriculum_id=row["curriculum_id"],
                    curriculum_unit_id=row["curriculum_unit_id"],
                    topic_id=row["topic_id"],
                    previous_state=row["state"],
                    new_state=row["state"],
                    reason="server_verified_failure",
                    attempt_id=result.attempt_id,
                    idempotency_key=result.attempt_id,
                    metadata={
                        "normalized_score": result.normalized_score,
                        "mastery_score": mastery_score,
                    },
                    created_at=now,
                )
                connection.commit()
                return self.repository.progress_from_row(updated)

            xp_delta = 0
            if (
                int(row["xp_awarded"]) == 0
                and result.source is not AssessmentSource.LEGACY_QUIZ
            ):
                xp_delta = CURRICULUM_UNIT_COMPLETION_XP
            transitioned = self._transition(
                connection,
                row,
                CurriculumUnitState.COMPLETED,
                now=now,
                assignments={
                    "mastery_score": mastery_score,
                    "mastery_band": mastery_band.value,
                    "attempt_count": attempt_count,
                    "xp_awarded": int(row["xp_awarded"]) + xp_delta,
                    "completed_at": now,
                },
            )
            self._award_xp(
                connection,
                user_id=user_id,
                subject=row["subject"],
                amount=xp_delta,
            )
            common = {
                "user_id": user_id,
                "curriculum_id": row["curriculum_id"],
                "curriculum_unit_id": row["curriculum_unit_id"],
                "topic_id": row["topic_id"],
                "previous_state": row["state"],
                "new_state": transitioned["state"],
                "attempt_id": result.attempt_id,
                "idempotency_key": result.attempt_id,
                "created_at": now,
            }
            self.repository.insert_event(
                connection,
                event_key=f"assessment-passed:{result.attempt_id}",
                event_type="curriculum_unit_assessment_passed",
                reason="server_verified_pass",
                metadata={"normalized_score": result.normalized_score},
                **common,
            )
            self.repository.insert_event(
                connection,
                event_key=f"unit-completed:{result.attempt_id}",
                event_type="curriculum_unit_completed",
                reason="assessment_passed",
                xp_delta=xp_delta,
                metadata={
                    "mastery_score": mastery_score,
                    "mastery_band": mastery_band.value,
                },
                **common,
            )
            self._recalculate_in_transaction(
                connection,
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
            )
            connection.commit()
            return self.repository.progress_from_row(transitioned)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_review_required(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        reason: ReviewReason,
        curriculum_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> CurriculumUnitProgress:
        if not isinstance(reason, ReviewReason):
            raise InvalidProgressTransition("A typed review reason is required.")
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._unit_for_update(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
                expected_version=expected_version,
                check_expected_version=False,
            )
            current = CurriculumUnitState(row["state"])
            if current is CurriculumUnitState.REVIEW_REQUIRED:
                connection.commit()
                return self.repository.progress_from_row(row)
            self._check_expected_version(row, expected_version)
            if current is not CurriculumUnitState.COMPLETED:
                raise InvalidProgressTransition("Only a completed unit can require review.")
            now = utc_now()
            transitioned = self._transition(
                connection,
                row,
                CurriculumUnitState.REVIEW_REQUIRED,
                now=now,
                assignments={
                    "mastery_band": MasteryBand.NEEDS_REVIEW.value,
                    "review_required_at": now,
                },
            )
            self.repository.insert_event(
                connection,
                event_key=f"review-required:{row['id']}:{row['version']}:{reason.value}",
                event_type="curriculum_unit_review_required",
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
                topic_id=row["topic_id"],
                previous_state=current.value,
                new_state=transitioned["state"],
                reason=reason.value,
                created_at=now,
            )
            connection.commit()
            return self.repository.progress_from_row(transitioned)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_review_result(
        self,
        *,
        user_id: int,
        curriculum_unit_id: str,
        result: ServerVerifiedAssessmentResult,
        curriculum_id: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> CurriculumUnitProgress:
        if (
            not isinstance(result, ServerVerifiedAssessmentResult)
            or result.source is not AssessmentSource.SERVER_REVIEW
        ):
            raise AssessmentEvidenceInvalid("A server-verified review result is required.")
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._unit_for_update(
                connection,
                user_id=user_id,
                curriculum_unit_id=curriculum_unit_id,
                curriculum_id=curriculum_id,
                expected_version=expected_version,
                check_expected_version=False,
            )
            if self._existing_assessment(
                connection,
                result=result,
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
            ):
                connection.commit()
                return self.repository.progress_from_row(row)
            self._check_expected_version(row, expected_version)
            if CurriculumUnitState(row["state"]) is not CurriculumUnitState.REVIEW_REQUIRED:
                raise InvalidProgressTransition("Unit is not waiting for review.")
            self._insert_assessment(
                connection,
                result=result,
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
                topic_id=row["topic_id"],
            )
            now = result.verified_at.isoformat(timespec="seconds")
            attempt_count = int(row["attempt_count"]) + 1
            if not result.passed:
                cursor = connection.execute(
                    """
                    UPDATE curriculum_unit_progress
                    SET attempt_count = ?, last_activity_at = ?, updated_at = ?,
                        version = version + 1
                    WHERE id = ? AND state = 'review_required' AND version = ?
                    """,
                    (attempt_count, now, now, row["id"], int(row["version"])),
                )
                if cursor.rowcount != 1:
                    raise ProgressConflict("Review progress changed concurrently.")
                updated = connection.execute(
                    "SELECT * FROM curriculum_unit_progress WHERE id = ?",
                    (row["id"],),
                ).fetchone()
                event_type = "curriculum_unit_assessment_failed"
                new_state = row["state"]
            else:
                score, band = mastery_after_assessment(
                    previous_score=row["mastery_score"],
                    normalized_score=result.normalized_score,
                    passed=True,
                )
                updated = self._transition(
                    connection,
                    row,
                    CurriculumUnitState.COMPLETED,
                    now=now,
                    assignments={
                        "attempt_count": attempt_count,
                        "mastery_score": score,
                        "mastery_band": band.value,
                        "completed_at": now,
                    },
                )
                event_type = "curriculum_unit_review_completed"
                new_state = updated["state"]
            self.repository.insert_event(
                connection,
                event_key=f"review-result:{result.attempt_id}",
                event_type=event_type,
                user_id=user_id,
                curriculum_id=row["curriculum_id"],
                curriculum_unit_id=row["curriculum_unit_id"],
                topic_id=row["topic_id"],
                previous_state=row["state"],
                new_state=new_state,
                reason=("review_passed" if result.passed else "review_failed"),
                attempt_id=result.attempt_id,
                idempotency_key=result.attempt_id,
                created_at=now,
            )
            if result.passed:
                self._recalculate_in_transaction(
                    connection,
                    user_id=user_id,
                    curriculum_id=row["curriculum_id"],
                )
            connection.commit()
            return self.repository.progress_from_row(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_checkpoint_result(
        self,
        *,
        user_id: int,
        curriculum_id: str,
        checkpoint_id: str,
        result: ServerVerifiedAssessmentResult,
        expected_version: Optional[int] = None,
    ) -> CurriculumCheckpointProgressView:
        if (
            not isinstance(result, ServerVerifiedAssessmentResult)
            or result.source is not AssessmentSource.CHECKPOINT_ASSESSMENT
        ):
            raise AssessmentEvidenceInvalid(
                "A server-verified checkpoint result is required."
            )
        connection = self.repository.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            curriculum = self.repository.curriculum_row(
                connection,
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
            self._assert_active(curriculum)
            row = connection.execute(
                """
                SELECT p.*, c.after_unit_order, c.topic_ids_json
                FROM curriculum_checkpoint_progress p
                JOIN ai_curriculum_checkpoints c
                  ON c.curriculum_id = p.curriculum_id AND c.checkpoint_id = p.checkpoint_id
                WHERE p.user_id = ? AND p.curriculum_id = ? AND p.checkpoint_id = ?
                """,
                (int(user_id), curriculum_id, checkpoint_id),
            ).fetchone()
            if row is None:
                raise CurriculumUnitNotFound("Curriculum checkpoint was not found.")
            if self._existing_assessment(
                connection,
                result=result,
                user_id=user_id,
                curriculum_id=curriculum_id,
                checkpoint_id=checkpoint_id,
            ):
                connection.commit()
                return self._checkpoint_view(row)
            self._check_expected_version(row, expected_version)
            if row["state"] != CheckpointState.AVAILABLE.value:
                raise InvalidProgressTransition("Checkpoint is not available.")
            self._insert_assessment(
                connection,
                result=result,
                user_id=user_id,
                curriculum_id=curriculum_id,
                checkpoint_id=checkpoint_id,
            )
            now = result.verified_at.isoformat(timespec="seconds")
            target = CheckpointState.COMPLETED if result.passed else CheckpointState.AVAILABLE
            cursor = connection.execute(
                """
                UPDATE curriculum_checkpoint_progress
                SET state = ?, attempt_count = attempt_count + 1,
                    completed_at = CASE WHEN ? = 'completed' THEN ? ELSE completed_at END,
                    last_activity_at = ?, updated_at = ?, version = version + 1
                WHERE id = ? AND state = 'available' AND version = ?
                """,
                (
                    target.value,
                    target.value,
                    now,
                    now,
                    now,
                    row["id"],
                    int(row["version"]),
                ),
            )
            if cursor.rowcount != 1:
                raise ProgressConflict("Checkpoint progress changed concurrently.")
            updated = connection.execute(
                """
                SELECT p.*, c.after_unit_order, c.topic_ids_json
                FROM curriculum_checkpoint_progress p
                JOIN ai_curriculum_checkpoints c
                  ON c.curriculum_id = p.curriculum_id AND c.checkpoint_id = p.checkpoint_id
                WHERE p.id = ?
                """,
                (row["id"],),
            ).fetchone()
            self.repository.insert_event(
                connection,
                event_key=f"checkpoint-result:{result.attempt_id}",
                event_type=(
                    "curriculum_checkpoint_passed"
                    if result.passed
                    else "curriculum_checkpoint_failed"
                ),
                user_id=user_id,
                curriculum_id=curriculum_id,
                checkpoint_id=checkpoint_id,
                previous_state=row["state"],
                new_state=target.value,
                reason=("checkpoint_passed" if result.passed else "checkpoint_failed"),
                attempt_id=result.attempt_id,
                idempotency_key=result.attempt_id,
                created_at=now,
            )
            if result.passed:
                self._recalculate_in_transaction(
                    connection,
                    user_id=user_id,
                    curriculum_id=curriculum_id,
                )
            connection.commit()
            return self._checkpoint_view(updated)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _checkpoint_view(row: sqlite3.Row) -> CurriculumCheckpointProgressView:
        state = CheckpointState(row["state"])
        return CurriculumCheckpointProgressView(
            checkpoint_id=row["checkpoint_id"],
            after_unit_order=int(row["after_unit_order"]),
            topic_ids=tuple(json.loads(row["topic_ids_json"] or "[]")),
            state=state,
            completed_at=row["completed_at"],
            next_allowed_action=(
                "await_server_verified_checkpoint"
                if state is CheckpointState.AVAILABLE
                else None
            ),
        )

    def _snapshot_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> CurriculumProgressSnapshot:
        curriculum = self.repository.curriculum_row(
            connection,
            user_id=user_id,
            curriculum_id=curriculum_id,
        )
        rows = connection.execute(
            """
            SELECT p.*, u.position, u.prerequisite_topic_ids_json
            FROM curriculum_unit_progress p
            JOIN ai_curriculum_units u
              ON u.curriculum_id = p.curriculum_id AND u.unit_id = p.curriculum_unit_id
            WHERE p.user_id = ? AND p.curriculum_id = ?
            ORDER BY u.position
            """,
            (int(user_id), curriculum_id),
        ).fetchall()
        if not rows:
            raise CurriculumProgressNotFound("Curriculum progress is not initialized.")
        checkpoint_rows = connection.execute(
            """
            SELECT p.*, c.after_unit_order, c.topic_ids_json
            FROM curriculum_checkpoint_progress p
            JOIN ai_curriculum_checkpoints c
              ON c.curriculum_id = p.curriculum_id AND c.checkpoint_id = p.checkpoint_id
            WHERE p.user_id = ? AND p.curriculum_id = ?
            ORDER BY c.position
            """,
            (int(user_id), curriculum_id),
        ).fetchall()
        unit_views = []
        for row in rows:
            prior_checkpoints = [
                checkpoint
                for checkpoint in checkpoint_rows
                if int(checkpoint["after_unit_order"]) < int(row["position"])
            ]
            if not prior_checkpoints:
                checkpoint_status = "not_required"
            elif all(
                checkpoint["state"] == CheckpointState.COMPLETED.value
                for checkpoint in prior_checkpoints
            ):
                checkpoint_status = "satisfied"
            else:
                checkpoint_status = "blocked"
            state = CurriculumUnitState(row["state"])
            topic = self.taxonomy.topics_by_id.get(row["topic_id"])
            unit_views.append(CurriculumUnitProgressView(
                unit_id=row["curriculum_unit_id"],
                topic_id=row["topic_id"],
                title=topic.title_uk if topic else row["topic_id"],
                order=int(row["position"]),
                state=state,
                mastery_score=(
                    None if row["mastery_score"] is None else float(row["mastery_score"])
                ),
                mastery_band=MasteryBand(row["mastery_band"]),
                prerequisite_topic_ids=tuple(
                    json.loads(row["prerequisite_topic_ids_json"] or "[]")
                ),
                checkpoint_status=checkpoint_status,
                completion_timestamp=row["completed_at"],
                next_allowed_action=next_allowed_action(state),
                version=int(row["version"]),
            ))
        checkpoint_views = tuple(self._checkpoint_view(row) for row in checkpoint_rows)
        completed = sum(
            view.state is CurriculumUnitState.COMPLETED for view in unit_views
        )
        available = sum(
            view.state is CurriculumUnitState.AVAILABLE for view in unit_views
        )
        in_progress = sum(view.state in ACTIVE_WORK_STATES for view in unit_views)
        locked = sum(view.state is CurriculumUnitState.LOCKED for view in unit_views)
        review_required = sum(
            view.state is CurriculumUnitState.REVIEW_REQUIRED for view in unit_views
        )
        current_states = {
            CurriculumUnitState.AVAILABLE,
            CurriculumUnitState.IN_PROGRESS,
            CurriculumUnitState.LESSON_COMPLETED,
            CurriculumUnitState.ASSESSMENT_REQUIRED,
            CurriculumUnitState.REVIEW_REQUIRED,
        }
        total = len(unit_views)
        return CurriculumProgressSnapshot(
            curriculum_id=curriculum_id,
            curriculum_version=int(curriculum["curriculum_version"]),
            subject=curriculum["subject"],
            curriculum_status=curriculum["status"],
            historical=curriculum["status"] != "published",
            total_units=total,
            completed_units=completed,
            available_units=available,
            in_progress_units=in_progress,
            locked_units=locked,
            review_required_units=review_required,
            completion_percent=round((completed / max(1, total)) * 100, 2),
            current_unit_ids=tuple(
                view.unit_id for view in unit_views if view.state in current_states
            ),
            units=tuple(unit_views),
            checkpoints=checkpoint_views,
        )

    def get_curriculum_progress(
        self,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> CurriculumProgressSnapshot:
        connection = self.repository.connect()
        try:
            curriculum = self.repository.curriculum_row(
                connection,
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
            count = int(connection.execute(
                """
                SELECT COUNT(*) FROM curriculum_unit_progress
                WHERE user_id = ? AND curriculum_id = ?
                """,
                (int(user_id), curriculum_id),
            ).fetchone()[0])
        finally:
            connection.close()
        if count == 0 and curriculum["status"] == "published":
            return self.initialize_curriculum_progress(
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
        if count == 0:
            raise CurriculumProgressNotFound("Historical curriculum progress was not found.")
        connection = self.repository.connect()
        try:
            return self._snapshot_in_transaction(
                connection,
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
        finally:
            connection.close()

    def get_active_curriculum_progress(
        self,
        *,
        user_id: int,
        subject: str,
    ) -> CurriculumProgressSnapshot:
        connection = self.repository.connect()
        try:
            row = connection.execute(
                """
                SELECT id FROM ai_curricula
                WHERE user_id = ? AND subject = ? AND status = 'published'
                """,
                (int(user_id), str(subject)),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise CurriculumProgressNotFound("No active curriculum was found.")
        return self.get_curriculum_progress(
            user_id=user_id,
            curriculum_id=row["id"],
        )
