import json
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from easynmt_core.progress import (
    AssessmentEvidenceInvalid,
    AssessmentSource,
    CheckpointState,
    CurriculumOwnershipError,
    CurriculumProgressRepository,
    CurriculumProgressService,
    CurriculumSuperseded,
    CurriculumUnitState,
    InvalidProgressTransition,
    LessonCompletionEvidence,
    LessonCompletionSource,
    PrerequisitesNotSatisfied,
    ProgressConflict,
    ProgressInitializationError,
    ReviewReason,
    ServerVerifiedAssessmentResult,
)


BASE_UNITS = (
    ("u-integers", "math.numbers.integers", ()),
    ("u-rational", "math.numbers.rational_real", ("math.numbers.integers",)),
    ("u-fractions", "math.numbers.fractions", ("math.numbers.integers",)),
    ("u-powers", "math.numbers.powers_roots", ("math.numbers.rational_real",)),
    (
        "u-expressions",
        "math.numbers.numeric_expressions",
        ("math.numbers.rational_real", "math.numbers.powers_roots"),
    ),
    ("u-percentages", "math.numbers.percentages", ("math.numbers.fractions",)),
)


def insert_curriculum_rows(
    connection,
    *,
    curriculum_id,
    user_id,
    version=1,
    status="published",
    units=BASE_UNITS,
    with_checkpoint=True,
    mastered_topic_ids=(),
    review_topic_ids=(),
):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    connection.execute(
        """
        INSERT INTO ai_curricula (
            id, user_id, subject, curriculum_version, taxonomy_version,
            schema_version, prompt_version, model_identifier, target_score,
            starting_level, status, creation_reason, generation_source,
            context_fingerprint, request_fingerprint, generation_metadata_json,
            created_at, published_at
        ) VALUES (?, ?, 'math', ?, 'nmt-math-v1', 'curriculum-v1', 'test-v1',
                  'deterministic-test', 170, 'average', ?, 'test_fixture',
                  'deterministic', ?, ?, ?, ?, ?)
        """,
        (
            curriculum_id,
            int(user_id),
            int(version),
            status,
            f"context-{curriculum_id}",
            f"request-{curriculum_id}",
            json.dumps({
                "mastered_topic_ids": list(mastered_topic_ids),
                "review_topic_ids": list(review_topic_ids),
            }),
            now,
            now if status == "published" else None,
        ),
    )
    review_topics = set(review_topic_ids)
    for position, (unit_id, topic_id, prerequisites) in enumerate(units, 1):
        connection.execute(
            """
            INSERT INTO ai_curriculum_units (
                curriculum_id, unit_id, position, topic_id,
                prerequisite_topic_ids_json, prerequisite_explanation,
                priority, difficulty, estimated_duration_minutes,
                study_sessions, mastery_target, reason_code
            ) VALUES (?, ?, ?, ?, ?, '', ?, 'adaptive', 30, 1, 0.75, ?)
            """,
            (
                curriculum_id,
                unit_id,
                position,
                topic_id,
                json.dumps(prerequisites),
                "optional" if position == len(units) else "core",
                "review_mastered" if topic_id in review_topics else "score_priority",
            ),
        )
    if with_checkpoint and len(units) >= 4:
        connection.execute(
            """
            INSERT INTO ai_curriculum_checkpoints (
                curriculum_id, checkpoint_id, position, after_unit_order,
                topic_ids_json, reason_code, estimated_minutes
            ) VALUES (?, ?, 1, 4, ?, 'spaced_review', 20)
            """,
            (
                curriculum_id,
                f"checkpoint-{curriculum_id}",
                json.dumps([topic_id for _, topic_id, _ in units[:4]]),
            ),
        )


class CurriculumProgressServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/progress.db"
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            INSERT INTO users (id, name) VALUES (1, 'Owner'), (2, 'Other');
            CREATE TABLE completed_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                lesson_id INTEGER NOT NULL,
                best_score INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, subject, lesson_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE user_subject_progress (
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                PRIMARY KEY(user_id, subject),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE user_plans (
                user_id INTEGER PRIMARY KEY,
                subject TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            INSERT INTO user_subject_progress (user_id, subject) VALUES (1, 'math'), (2, 'math');
            INSERT INTO user_plans (user_id, subject) VALUES (1, 'math'), (2, 'math');
            """
        )
        connection.commit()
        connection.close()

        from easynmt_ai.curriculum import CurriculumRepository

        self.curriculum_repository = CurriculumRepository(self.db_path)
        self.curriculum_repository.ensure_schema()
        self.repository = CurriculumProgressRepository(self.db_path)
        self.repository.ensure_schema()
        self.service = CurriculumProgressService(self.repository)
        self.curriculum_id = "curriculum-one"
        connection = self.repository.connect()
        insert_curriculum_rows(
            connection,
            curriculum_id=self.curriculum_id,
            user_id=1,
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def initialize(self):
        return self.service.initialize_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        )

    def unit(self, topic_id, curriculum_id=None):
        snapshot = self.service.get_curriculum_progress(
            user_id=1,
            curriculum_id=curriculum_id or self.curriculum_id,
        )
        return next(item for item in snapshot.units if item.topic_id == topic_id)

    def lesson_evidence(self, suffix, *, when=None):
        return LessonCompletionEvidence(
            evidence_id=f"lesson-{suffix}",
            verified_at=when or datetime.now(timezone.utc),
            source=LessonCompletionSource.SERVER_LESSON,
        )

    def assessment(self, suffix, *, passed=True, score=None, source=AssessmentSource.SERVER_QUIZ):
        return ServerVerifiedAssessmentResult(
            passed=passed,
            score=(8 if passed else 3) if score is None else score,
            max_score=10,
            attempt_id=f"attempt-{suffix}",
            verified_at=datetime.now(timezone.utc),
            source=source,
        )

    def prepare_assessment(self, unit_id, suffix):
        started = self.service.start_curriculum_unit(
            user_id=1,
            curriculum_unit_id=unit_id,
            curriculum_id=self.curriculum_id,
        )
        lesson = self.service.mark_lesson_completed(
            user_id=1,
            curriculum_unit_id=unit_id,
            curriculum_id=self.curriculum_id,
            completion_evidence=self.lesson_evidence(suffix),
        )
        required = self.service.mark_assessment_required(
            user_id=1,
            curriculum_unit_id=unit_id,
            curriculum_id=self.curriculum_id,
        )
        self.assertEqual(started.state, CurriculumUnitState.IN_PROGRESS)
        self.assertEqual(lesson.state, CurriculumUnitState.LESSON_COMPLETED)
        self.assertEqual(required.state, CurriculumUnitState.ASSESSMENT_REQUIRED)
        return required

    def complete(self, topic_id, suffix):
        unit = self.unit(topic_id)
        self.prepare_assessment(unit.unit_id, suffix)
        return self.service.record_assessment_result(
            user_id=1,
            curriculum_unit_id=unit.unit_id,
            curriculum_id=self.curriculum_id,
            result=self.assessment(suffix),
        )

    def xp_values(self):
        connection = self.repository.connect()
        try:
            subject_xp = connection.execute(
                "SELECT xp FROM user_subject_progress WHERE user_id = 1 AND subject = 'math'"
            ).fetchone()[0]
            plan_xp = connection.execute(
                "SELECT xp FROM user_plans WHERE user_id = 1"
            ).fetchone()[0]
            return int(subject_xp), int(plan_xp)
        finally:
            connection.close()

    def test_schema_constraints_indexes_and_repeatable_upgrade(self):
        self.repository.ensure_schema()
        self.initialize()
        connection = self.repository.connect()
        try:
            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertTrue({
                "curriculum_unit_progress",
                "curriculum_checkpoint_progress",
                "curriculum_topic_credits",
                "curriculum_assessment_results",
                "curriculum_progress_events",
            }.issubset(table_names))
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            self.assertTrue({
                "idx_curriculum_progress_active",
                "idx_curriculum_progress_topic",
                "idx_curriculum_checkpoint_active",
                "idx_curriculum_progress_events_lookup",
            }.issubset(indexes))
            progress_id = connection.execute(
                "SELECT id FROM curriculum_unit_progress LIMIT 1"
            ).fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE curriculum_unit_progress SET state = 'browser_completed' WHERE id = ?",
                    (progress_id,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE curriculum_unit_progress SET mastery_score = 1.5 WHERE id = ?",
                    (progress_id,),
                )
            connection.rollback()
            row = connection.execute(
                "SELECT * FROM curriculum_unit_progress LIMIT 1"
            ).fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO curriculum_unit_progress (
                        id, user_id, curriculum_id, curriculum_unit_id, topic_id,
                        state, mastery_band, last_activity_at, source, created_at, updated_at
                    ) VALUES ('duplicate', ?, ?, ?, ?, 'locked', 'unknown', ?, 'curriculum', ?, ?)
                    """,
                    (row["user_id"], row["curriculum_id"], row["curriculum_unit_id"], row["topic_id"],
                     row["last_activity_at"], row["created_at"], row["updated_at"]),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO curriculum_unit_progress (
                        id, user_id, curriculum_id, curriculum_unit_id, topic_id,
                        state, mastery_band, last_activity_at, source, created_at, updated_at
                    ) VALUES ('cross-owner', 2, ?, ?, ?, 'locked', 'unknown', ?, 'curriculum', ?, ?)
                    """,
                    (row["curriculum_id"], row["curriculum_unit_id"], row["topic_id"],
                     row["last_activity_at"], row["created_at"], row["updated_at"]),
                )
        finally:
            connection.rollback()
            connection.close()

    def test_initialization_is_atomic_idempotent_and_owner_scoped(self):
        snapshot = self.initialize()
        self.assertEqual(snapshot.total_units, len(BASE_UNITS))
        self.assertEqual(snapshot.available_units, 1)
        self.assertEqual(self.unit("math.numbers.integers").state, CurriculumUnitState.AVAILABLE)
        self.assertEqual(self.unit("math.numbers.rational_real").state, CurriculumUnitState.LOCKED)

        again = self.initialize()
        self.assertEqual(again.total_units, len(BASE_UNITS))
        connection = self.repository.connect()
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_unit_progress WHERE curriculum_id = ?",
                (self.curriculum_id,),
            ).fetchone()[0], len(BASE_UNITS))
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_progress_events WHERE event_type = 'curriculum_progress_initialized'"
            ).fetchone()[0], 1)
        finally:
            connection.close()
        with self.assertRaises(CurriculumOwnershipError):
            self.service.initialize_curriculum_progress(user_id=2, curriculum_id=self.curriculum_id)

    def test_initialization_failure_and_partial_state_are_rejected_atomically(self):
        connection = self.repository.connect()
        connection.executescript(
            """
            CREATE TRIGGER fail_progress_initialization
            BEFORE INSERT ON curriculum_unit_progress
            WHEN NEW.topic_id = 'math.numbers.fractions'
            BEGIN
                SELECT RAISE(ABORT, 'injected progress failure');
            END;
            """
        )
        connection.commit()
        connection.close()
        with self.assertRaises(sqlite3.IntegrityError):
            self.initialize()
        connection = self.repository.connect()
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_unit_progress"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_progress_events"
            ).fetchone()[0], 0)
            connection.execute("DROP TRIGGER fail_progress_initialization")
            connection.execute(
                """
                INSERT INTO curriculum_checkpoint_progress (
                    id, user_id, curriculum_id, checkpoint_id, state,
                    last_activity_at, created_at, updated_at
                ) VALUES ('partial', 1, ?, ?, 'locked', 'now', 'now', 'now')
                """,
                (self.curriculum_id, f"checkpoint-{self.curriculum_id}"),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(ProgressInitializationError):
            self.initialize()
        connection = self.repository.connect()
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_unit_progress"
            ).fetchone()[0], 0)
        finally:
            connection.close()

    def test_state_machine_verified_failure_pass_review_and_mastery(self):
        self.initialize()
        root = self.unit("math.numbers.integers")
        with self.assertRaises(InvalidProgressTransition):
            self.service.mark_assessment_required(user_id=1, curriculum_unit_id=root.unit_id)
        with self.assertRaises(InvalidProgressTransition):
            self.service.mark_lesson_completed(
                user_id=1,
                curriculum_unit_id=root.unit_id,
                completion_evidence={"completed": True},
            )
        self.prepare_assessment(root.unit_id, "root")
        failed = self.service.record_assessment_result(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            result=self.assessment("root-fail", passed=False),
        )
        self.assertEqual(failed.state, CurriculumUnitState.ASSESSMENT_REQUIRED)
        self.assertEqual(failed.attempt_count, 1)
        self.assertEqual(failed.mastery_band.value, "developing")
        self.assertEqual(self.xp_values(), (0, 0))
        passed_result = self.assessment("root-pass", passed=True)
        completed = self.service.record_assessment_result(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            result=passed_result,
        )
        self.assertEqual(completed.state, CurriculumUnitState.COMPLETED)
        self.assertEqual(completed.attempt_count, 2)
        self.assertEqual(completed.mastery_band.value, "proficient")
        self.assertLess(completed.mastery_score, 1.0)
        self.assertEqual(self.xp_values(), (60, 60))

        review = self.service.mark_review_required(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            reason=ReviewReason.MASTERY_DECAY,
        )
        self.assertEqual(review.state, CurriculumUnitState.REVIEW_REQUIRED)
        reviewed = self.service.record_review_result(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            result=self.assessment(
                "root-review",
                passed=True,
                source=AssessmentSource.SERVER_REVIEW,
            ),
        )
        self.assertEqual(reviewed.state, CurriculumUnitState.COMPLETED)
        self.assertEqual(self.xp_values(), (60, 60))

    def test_evidence_contracts_and_conflicting_idempotency_keys_are_rejected(self):
        self.initialize()
        root = self.unit("math.numbers.integers")
        started = self.service.start_curriculum_unit(user_id=1, curriculum_unit_id=root.unit_id)
        when = datetime.now(timezone.utc).replace(microsecond=0)
        evidence = self.lesson_evidence("immutable", when=when)
        completed = self.service.mark_lesson_completed(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            completion_evidence=evidence,
            expected_version=started.version,
        )
        repeated = self.service.mark_lesson_completed(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            completion_evidence=evidence,
            expected_version=started.version,
        )
        self.assertEqual(completed.version, repeated.version)
        changed = self.lesson_evidence("immutable", when=when + timedelta(seconds=1))
        with self.assertRaises(InvalidProgressTransition):
            self.service.mark_lesson_completed(
                user_id=1,
                curriculum_unit_id=root.unit_id,
                completion_evidence=changed,
            )

        self.service.mark_assessment_required(user_id=1, curriculum_unit_id=root.unit_id)
        result = self.assessment("immutable")
        self.service.record_assessment_result(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            result=result,
        )
        conflicting = ServerVerifiedAssessmentResult(
            passed=False,
            score=2,
            max_score=10,
            attempt_id=result.attempt_id,
            verified_at=result.verified_at,
            source=result.source,
        )
        with self.assertRaises(AssessmentEvidenceInvalid):
            self.service.record_assessment_result(
                user_id=1,
                curriculum_unit_id=root.unit_id,
                result=conflicting,
            )

    def test_prerequisites_branching_checkpoint_and_optional_unlocking(self):
        self.initialize()
        self.complete("math.numbers.integers", "integers")
        snapshot = self.service.get_curriculum_progress(user_id=1, curriculum_id=self.curriculum_id)
        available = {unit.topic_id for unit in snapshot.units if unit.state is CurriculumUnitState.AVAILABLE}
        self.assertEqual(available, {"math.numbers.rational_real", "math.numbers.fractions"})

        self.complete("math.numbers.rational_real", "rational")
        self.complete("math.numbers.fractions", "fractions")
        self.assertEqual(self.unit("math.numbers.powers_roots").state, CurriculumUnitState.AVAILABLE)
        with self.assertRaises(PrerequisitesNotSatisfied):
            self.service.start_curriculum_unit(
                user_id=1,
                curriculum_unit_id="u-expressions",
                curriculum_id=self.curriculum_id,
            )
        self.complete("math.numbers.powers_roots", "powers")
        before_checkpoint = self.service.get_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        )
        checkpoint = before_checkpoint.checkpoints[0]
        self.assertEqual(checkpoint.state, CheckpointState.AVAILABLE)
        self.assertEqual(self.unit("math.numbers.numeric_expressions").state, CurriculumUnitState.LOCKED)
        self.assertEqual(self.unit("math.numbers.percentages").state, CurriculumUnitState.LOCKED)

        failed = self.service.record_checkpoint_result(
            user_id=1,
            curriculum_id=self.curriculum_id,
            checkpoint_id=checkpoint.checkpoint_id,
            result=self.assessment(
                "checkpoint-fail",
                passed=False,
                source=AssessmentSource.CHECKPOINT_ASSESSMENT,
            ),
        )
        self.assertEqual(failed.state, CheckpointState.AVAILABLE)
        passed = self.service.record_checkpoint_result(
            user_id=1,
            curriculum_id=self.curriculum_id,
            checkpoint_id=checkpoint.checkpoint_id,
            result=self.assessment(
                "checkpoint-pass",
                source=AssessmentSource.CHECKPOINT_ASSESSMENT,
            ),
        )
        self.assertEqual(passed.state, CheckpointState.COMPLETED)
        after_checkpoint = self.service.get_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        )
        available = {unit.topic_id for unit in after_checkpoint.units if unit.state is CurriculumUnitState.AVAILABLE}
        self.assertEqual(available, {"math.numbers.numeric_expressions", "math.numbers.percentages"})
        recalculated = self.service.recalculate_unlocks(user_id=1, curriculum_id=self.curriculum_id)
        self.assertTrue(recalculated.unchanged)

    def test_review_credit_does_not_unlock_dependents_until_verified(self):
        connection = self.repository.connect()
        connection.execute("UPDATE ai_curricula SET status = 'superseded' WHERE id = ?", (self.curriculum_id,))
        review_curriculum = "review-curriculum"
        insert_curriculum_rows(
            connection,
            curriculum_id=review_curriculum,
            user_id=1,
            version=2,
            units=BASE_UNITS[:2],
            with_checkpoint=False,
            mastered_topic_ids=("math.numbers.integers",),
            review_topic_ids=("math.numbers.integers",),
        )
        connection.commit()
        connection.close()
        snapshot = self.service.initialize_curriculum_progress(
            user_id=1,
            curriculum_id=review_curriculum,
        )
        root, dependent = snapshot.units
        self.assertEqual(root.state, CurriculumUnitState.REVIEW_REQUIRED)
        self.assertEqual(dependent.state, CurriculumUnitState.LOCKED)
        self.service.record_review_result(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            curriculum_id=review_curriculum,
            result=self.assessment(
                "credited-review",
                source=AssessmentSource.SERVER_REVIEW,
            ),
        )
        self.assertEqual(
            self.service.get_curriculum_progress(
                user_id=1,
                curriculum_id=review_curriculum,
            ).units[1].state,
            CurriculumUnitState.AVAILABLE,
        )

    def test_concurrent_retries_do_not_duplicate_state_events_or_xp(self):
        self.initialize()
        root = self.unit("math.numbers.integers")
        with ThreadPoolExecutor(max_workers=4) as pool:
            starts = list(pool.map(
                lambda _: self.service.start_curriculum_unit(
                    user_id=1,
                    curriculum_unit_id=root.unit_id,
                    curriculum_id=self.curriculum_id,
                ),
                range(4),
            ))
        self.assertTrue(all(item.state is CurriculumUnitState.IN_PROGRESS for item in starts))
        evidence = self.lesson_evidence("parallel")
        with ThreadPoolExecutor(max_workers=4) as pool:
            lessons = list(pool.map(
                lambda _: self.service.mark_lesson_completed(
                    user_id=1,
                    curriculum_unit_id=root.unit_id,
                    curriculum_id=self.curriculum_id,
                    completion_evidence=evidence,
                ),
                range(4),
            ))
        self.assertTrue(all(item.state is CurriculumUnitState.LESSON_COMPLETED for item in lessons))
        self.service.mark_assessment_required(user_id=1, curriculum_unit_id=root.unit_id)
        result = self.assessment("parallel")
        with ThreadPoolExecutor(max_workers=4) as pool:
            completions = list(pool.map(
                lambda _: self.service.record_assessment_result(
                    user_id=1,
                    curriculum_unit_id=root.unit_id,
                    curriculum_id=self.curriculum_id,
                    result=result,
                ),
                range(4),
            ))
        self.assertTrue(all(item.state is CurriculumUnitState.COMPLETED for item in completions))
        self.assertEqual(self.xp_values(), (60, 60))
        events = self.repository.list_events(user_id=1, curriculum_id=self.curriculum_id)
        self.assertEqual(sum(event["event_type"] == "curriculum_unit_started" for event in events), 1)
        self.assertEqual(sum(event["event_type"] == "curriculum_unit_lesson_completed" for event in events), 1)
        self.assertEqual(sum(event["event_type"] == "curriculum_unit_completed" for event in events), 1)

    def test_concurrent_initialization_and_stale_updates_are_safe(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            snapshots = list(pool.map(
                lambda _: self.service.initialize_curriculum_progress(
                    user_id=1,
                    curriculum_id=self.curriculum_id,
                ),
                range(4),
            ))
        self.assertTrue(all(snapshot.total_units == len(BASE_UNITS) for snapshot in snapshots))
        root = self.unit("math.numbers.integers")
        started = self.service.start_curriculum_unit(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            expected_version=root.version,
        )
        repeated = self.service.start_curriculum_unit(
            user_id=1,
            curriculum_unit_id=root.unit_id,
            expected_version=root.version,
        )
        self.assertEqual(started.version, repeated.version)
        with self.assertRaises(ProgressConflict):
            self.service.mark_lesson_completed(
                user_id=1,
                curriculum_unit_id=root.unit_id,
                expected_version=root.version,
                completion_evidence=self.lesson_evidence("stale"),
            )

    def test_xp_and_progress_roll_back_together(self):
        self.initialize()
        root = self.unit("math.numbers.integers")
        self.prepare_assessment(root.unit_id, "rollback")
        connection = self.repository.connect()
        connection.executescript(
            """
            CREATE TRIGGER fail_after_xp_update
            BEFORE INSERT ON curriculum_progress_events
            WHEN NEW.event_type = 'curriculum_unit_completed'
            BEGIN
                SELECT RAISE(ABORT, 'injected event failure');
            END;
            """
        )
        connection.commit()
        connection.close()
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.record_assessment_result(
                user_id=1,
                curriculum_unit_id=root.unit_id,
                result=self.assessment("rollback"),
            )
        self.assertEqual(self.repository.get_progress(
            user_id=1,
            curriculum_unit_id=root.unit_id,
        ).state, CurriculumUnitState.ASSESSMENT_REQUIRED)
        self.assertEqual(self.xp_values(), (0, 0))
        connection = self.repository.connect()
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_assessment_results WHERE attempt_id = 'attempt-rollback'"
            ).fetchone()[0], 0)
        finally:
            connection.close()

    def test_legacy_completion_credit_and_quiz_adapter_preserve_existing_xp(self):
        connection = self.repository.connect()
        connection.execute("UPDATE user_subject_progress SET xp = 123 WHERE user_id = 1")
        connection.execute("UPDATE user_plans SET xp = 456 WHERE user_id = 1")
        connection.execute("UPDATE ai_curricula SET status = 'superseded' WHERE id = ?", (self.curriculum_id,))
        legacy_curriculum = "legacy-curriculum"
        insert_curriculum_rows(
            connection,
            curriculum_id=legacy_curriculum,
            user_id=1,
            version=2,
            units=(("u-quadratic", "math.algebra.quadratic_equations", ()),),
            with_checkpoint=False,
        )
        connection.commit()
        connection.close()
        snapshot = self.service.initialize_curriculum_progress(
            user_id=1,
            curriculum_id=legacy_curriculum,
        )
        unit = snapshot.units[0]
        self.assertEqual(unit.state, CurriculumUnitState.AVAILABLE)
        self.service.start_curriculum_unit(
            user_id=1,
            curriculum_unit_id=unit.unit_id,
            curriculum_id=legacy_curriculum,
        )
        connection = self.repository.connect()
        connection.execute(
            "INSERT INTO completed_lessons (user_id, subject, lesson_id, best_score, total) VALUES (1, 'math', 1, 8, 10)"
        )
        connection.commit()
        connection.close()
        self.service.mark_lesson_completed(
            user_id=1,
            curriculum_unit_id=unit.unit_id,
            curriculum_id=legacy_curriculum,
            completion_evidence=LessonCompletionEvidence(
                evidence_id="legacy-lesson-1-completion",
                verified_at=datetime.now(timezone.utc),
                source=LessonCompletionSource.LEGACY_LESSON,
                legacy_lesson_id=1,
            ),
        )
        self.service.mark_assessment_required(
            user_id=1,
            curriculum_unit_id=unit.unit_id,
            curriculum_id=legacy_curriculum,
        )
        completed = self.service.record_assessment_result(
            user_id=1,
            curriculum_unit_id=unit.unit_id,
            curriculum_id=legacy_curriculum,
            result=self.assessment(
                "legacy-quiz",
                source=AssessmentSource.LEGACY_QUIZ,
            ),
        )
        self.assertEqual(completed.xp_awarded, 0)
        self.assertEqual(self.xp_values(), (123, 456))

    def test_replacement_maps_only_completed_topic_ids_and_keeps_history(self):
        self.initialize()
        self.complete("math.numbers.integers", "old-integers")
        connection = self.repository.connect()
        connection.execute(
            "UPDATE ai_curricula SET status = 'superseded', superseded_at = CURRENT_TIMESTAMP WHERE id = ?",
            (self.curriculum_id,),
        )
        replacement_id = "curriculum-two"
        insert_curriculum_rows(
            connection,
            curriculum_id=replacement_id,
            user_id=1,
            version=2,
            units=(
                ("new-integers", "math.numbers.integers", ()),
                ("new-percentages", "math.numbers.percentages", ("math.numbers.fractions",)),
            ),
            with_checkpoint=False,
        )
        connection.commit()
        connection.close()
        replacement = self.service.initialize_curriculum_progress(
            user_id=1,
            curriculum_id=replacement_id,
        )
        self.assertEqual(replacement.units[0].state, CurriculumUnitState.COMPLETED)
        self.assertEqual(replacement.units[1].state, CurriculumUnitState.LOCKED)
        historical = self.service.get_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        )
        self.assertTrue(historical.historical)
        with self.assertRaises(CurriculumSuperseded):
            self.service.start_curriculum_unit(
                user_id=1,
                curriculum_unit_id="u-rational",
                curriculum_id=self.curriculum_id,
            )
        events = self.repository.list_events(user_id=1, curriculum_id=replacement_id)
        migrated = [event for event in events if event["event_type"] == "curriculum_progress_migrated"]
        self.assertEqual([event["topic_id"] for event in migrated], ["math.numbers.integers"])
        self.assertEqual(self.xp_values(), (60, 60))

    def test_read_model_counts_actions_and_authorization(self):
        self.initialize()
        self.complete("math.numbers.integers", "read-model")
        snapshot = self.service.get_curriculum_progress(user_id=1, curriculum_id=self.curriculum_id)
        self.assertEqual(snapshot.completed_units, 1)
        self.assertEqual(snapshot.available_units, 2)
        self.assertEqual(snapshot.locked_units, 3)
        self.assertEqual(snapshot.completion_percent, 16.67)
        root = next(unit for unit in snapshot.units if unit.topic_id == "math.numbers.integers")
        locked = next(unit for unit in snapshot.units if unit.topic_id == "math.numbers.powers_roots")
        available = next(unit for unit in snapshot.units if unit.topic_id == "math.numbers.fractions")
        self.assertIsNone(root.next_allowed_action)
        self.assertIsNone(locked.next_allowed_action)
        self.assertEqual(available.next_allowed_action, "start_lesson")
        with self.assertRaises(CurriculumOwnershipError):
            self.service.get_curriculum_progress(user_id=2, curriculum_id=self.curriculum_id)
        with self.assertRaises(CurriculumOwnershipError):
            self.service.start_curriculum_unit(user_id=2, curriculum_unit_id=available.unit_id)


class CurriculumProgressApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_security import app_module

        cls.app_module = app_module

    def setUp(self):
        self.app_module.app.config.update(TESTING=True)
        self.client = self.app_module.app.test_client()
        token = uuid.uuid4().hex
        connection = self.app_module.get_db_connection()
        cursor = connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Progress API", f"progress-{token}@example.com", "unused"),
        )
        self.user_id = int(cursor.lastrowid)
        other = connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Progress Other", f"progress-other-{token}@example.com", "unused"),
        )
        self.other_user_id = int(other.lastrowid)
        connection.execute(
            "INSERT INTO user_plans (user_id, subject) VALUES (?, 'math')",
            (self.user_id,),
        )
        self.curriculum_id = f"api-curriculum-{token}"
        self.unit_id = f"api-unit-{token}"
        insert_curriculum_rows(
            connection,
            curriculum_id=self.curriculum_id,
            user_id=self.user_id,
            units=((self.unit_id, "math.numbers.integers", ()),),
            with_checkpoint=False,
        )
        connection.commit()
        connection.close()
        self.app_module.curriculum_progress_service.initialize_curriculum_progress(
            user_id=self.user_id,
            curriculum_id=self.curriculum_id,
        )
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = self.user_id
            user_session["user_name"] = "Progress API"
            user_session["subject"] = "math"
            user_session["_csrf_token"] = token
        self.csrf_token = token

    def test_api_auth_csrf_subject_and_payload_boundaries(self):
        unauthenticated = self.app_module.app.test_client()
        self.assertEqual(unauthenticated.get("/api/curriculum/progress").status_code, 401)
        response = self.client.get("/api/curriculum/progress")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["progress"]["curriculum_id"], self.curriculum_id)

        self.assertEqual(
            self.client.post(f"/api/curriculum/units/{self.unit_id}/start", json={}).status_code,
            400,
        )
        rejected = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/start",
            json={"user_id": self.other_user_id, "state": "completed", "xp": 9999},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(rejected.status_code, 400)
        started = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/start",
            json={},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.get_json()["unit"]["state"], "in_progress")

        with self.client.session_transaction() as user_session:
            user_session["subject"] = "english"
        subject_mismatch = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/start",
            json={},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(subject_mismatch.status_code, 404)

    def test_api_does_not_read_or_mutate_another_account(self):
        other_client = self.app_module.app.test_client()
        with other_client.session_transaction() as user_session:
            user_session["user_id"] = self.other_user_id
            user_session["user_name"] = "Progress Other"
            user_session["subject"] = "math"
            user_session["_csrf_token"] = self.csrf_token
        self.assertEqual(other_client.get("/api/curriculum/progress").status_code, 404)
        response = other_client.post(
            f"/api/curriculum/units/{self.unit_id}/start",
            json={},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
