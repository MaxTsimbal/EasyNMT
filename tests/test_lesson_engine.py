import json
import logging
import sqlite3
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from flask import template_rendered

from easynmt_ai import AIContext, AIErrorCode, AIOrchestrator, AIResult, LessonEngine
from easynmt_ai.lessons import (
    LESSON_SECTION_ORDER,
    LessonGenerationRequest,
    LessonPrerequisite,
    validate_lesson,
)
from easynmt_ai.prompts.lesson import build_lesson_prompt
from easynmt_ai.curriculum import CurriculumRepository
from easynmt_core.lessons import (
    CurriculumLessonConflict,
    CurriculumLessonDeliveryInvalid,
    CurriculumLessonGenerationUnavailable,
    CurriculumLessonNotAvailable,
    CurriculumLessonOwnershipError,
    CurriculumLessonPersistenceError,
    CurriculumLessonRepository,
    CurriculumLessonService,
)
from easynmt_core.progress import (
    CurriculumProgressRepository,
    CurriculumProgressService,
    CurriculumUnitState,
)
from tests.lesson_fixtures import valid_lesson_proposal
from tests.test_curriculum_progress import insert_curriculum_rows


class FakeGateway:
    def __init__(self, *responses):
        self.enabled = True
        self.model = "test-lesson-model"
        self.responses = list(responses)
        self.calls = []
        self._lock = threading.Lock()

    def complete_custom(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
            if not self.responses:
                raise AssertionError("Unexpected repeated lesson generation")
            return self.responses.pop(0)


def ai_response(payload):
    return AIResult(
        json.dumps(payload, ensure_ascii=False),
        "openai",
        response_id="lesson-response",
        usage={"input_tokens": 1200, "output_tokens": 2400, "total_tokens": 3600},
    )


def engine_request(*, prerequisites=()):
    return LessonGenerationRequest(
        lesson_id="lesson-test",
        curriculum_id="curriculum-test",
        curriculum_unit_id="unit-test",
        topic_id="math.numbers.integers",
        subject="math",
        title="Цілі числа",
        description="Правила дій із цілими числами та перевірка результату.",
        objectives=("Виконувати дії з цілими числами.",),
        competencies=("Застосовує правила знаків.", "Перевіряє числовий результат."),
        prerequisites=tuple(prerequisites),
        difficulty="foundation",
        estimated_minutes=30,
        mastery_target=0.75,
        target_score=170,
        language="uk",
    )


def engine_context():
    return AIContext(
        user_id=1,
        subject="math",
        goal_score=170,
        known_weaknesses=("правила знаків",),
        recent_mistakes=("raw private answer that must not enter lesson prompt",),
        xp=900,
        language="uk",
        difficulty="foundation",
        available_tokens=6500,
        active_curriculum_id="curriculum-test",
    )


class LessonEngineContractTests(unittest.TestCase):
    def setUp(self):
        self.request = engine_request()
        self.context = engine_context()

    def test_complete_lesson_has_deterministic_order_and_quiz_contract(self):
        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        result = LessonEngine(AIOrchestrator(_gateway=gateway)).generate(
            self.context,
            self.request,
        )
        self.assertTrue(result.success)
        lesson = result.value
        self.assertEqual(lesson.section_order, LESSON_SECTION_ORDER)
        self.assertTrue(validate_lesson(lesson, self.request).valid)
        self.assertEqual([item.difficulty for item in lesson.worked_examples], [
            "foundation", "guided", "exam",
        ])
        quiz_input = lesson.for_quiz()
        self.assertEqual(quiz_input["lesson_id"], lesson.id)
        self.assertEqual(
            set(quiz_input["assessment_blueprint"]["covered_concept_ids"]),
            {item.id for item in lesson.concepts},
        )
        self.assertNotIn("generation_metadata", quiz_input)

    def test_incomplete_provider_output_is_rejected_without_fallback(self):
        invalid = valid_lesson_proposal(competency_count=2)
        invalid["worked_examples"] = invalid["worked_examples"][:1]
        result = LessonEngine(
            AIOrchestrator(_gateway=FakeGateway(ai_response(invalid)))
        ).generate(self.context, self.request)
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, AIErrorCode.VALIDATION_ERROR)
        self.assertFalse(result.fallback_used)

    def test_prompt_uses_separate_teaching_obligations_and_safe_context(self):
        prompt = build_lesson_prompt(self.context, self.request)
        for obligation in (
            "Teach one concept at a time",
            "Write at least three distinct examples",
            "Diagnose at least three realistic mistakes",
            "Finish with a compact recap",
            "Write like a patient experienced Ukrainian tutor",
        ):
            self.assertIn(obligation, prompt.instructions)
        prompt_payload = json.loads(prompt.user_input)
        self.assertEqual(prompt_payload["section_order"], [
            "learning objective",
            "why this matters for NMT",
            "prerequisite reminder when required",
            "core explanation",
            "worked examples",
            "common mistakes",
            "practical tips",
            "mini recap",
            "assessment transition",
        ])
        self.assertNotIn("raw private answer", prompt.user_input)
        self.assertNotIn('"user_id"', prompt.user_input)
        self.assertNotIn('"xp"', prompt.user_input)
        self.assertIn("правила знаків", prompt.user_input)

    def test_prerequisite_policy_is_authoritative(self):
        prerequisite = LessonPrerequisite(
            topic_id="math.numbers.integers",
            title="Цілі числа",
        )
        request = engine_request(prerequisites=(prerequisite,))
        payload = valid_lesson_proposal(
            competency_count=2,
            prerequisite_needed=False,
        )
        result = LessonEngine(
            AIOrchestrator(_gateway=FakeGateway(ai_response(payload)))
        ).generate(self.context, request)
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, AIErrorCode.VALIDATION_ERROR)


class CurriculumLessonServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/lessons.db"
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            INSERT INTO users (id, name) VALUES (1, 'Owner'), (2, 'Other');
            CREATE TABLE completed_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                lesson_id INTEGER NOT NULL,
                best_score INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, subject, lesson_id)
            );
            CREATE TABLE user_subject_progress (
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                PRIMARY KEY(user_id, subject)
            );
            CREATE TABLE user_plans (
                user_id INTEGER PRIMARY KEY,
                subject TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            INSERT INTO user_subject_progress (user_id, subject, xp)
            VALUES (1, 'math', 15), (2, 'math', 20);
            INSERT INTO user_plans (user_id, subject, xp)
            VALUES (1, 'math', 15), (2, 'math', 20);
            """
        )
        connection.commit()
        connection.close()
        CurriculumRepository(self.db_path).ensure_schema()
        self.progress_repository = CurriculumProgressRepository(self.db_path)
        self.progress_repository.ensure_schema()
        self.progress_service = CurriculumProgressService(self.progress_repository)
        self.curriculum_id = "curriculum-lessons"
        self.unit_id = "unit-integers"
        connection = self.progress_repository.connect()
        insert_curriculum_rows(
            connection,
            curriculum_id=self.curriculum_id,
            user_id=1,
            units=((self.unit_id, "math.numbers.integers", ()),),
            with_checkpoint=False,
        )
        connection.commit()
        connection.close()
        self.progress_service.initialize_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        )
        self.lesson_repository = CurriculumLessonRepository(self.db_path)
        self.lesson_repository.ensure_schema()
        self.gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        engine = LessonEngine(AIOrchestrator(_gateway=self.gateway))
        logger = logging.getLogger(f"tests.lesson.service.{id(self)}")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        self.service = CurriculumLessonService(
            self.lesson_repository,
            engine,
            self.progress_service,
            logger=logger,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def start(self):
        return self.progress_service.start_curriculum_unit(
            user_id=1,
            curriculum_id=self.curriculum_id,
            curriculum_unit_id=self.unit_id,
        )

    def progress(self):
        return self.progress_service.get_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        ).units[0]

    def test_unit_must_be_started_before_generation(self):
        with self.assertRaises(CurriculumLessonNotAvailable):
            self.service.deliver_lesson(
                user_id=1,
                curriculum_unit_id=self.unit_id,
                subject="math",
            )
        self.assertEqual(len(self.gateway.calls), 0)

    def test_generation_is_persistent_cached_and_delivery_secret_is_hashed(self):
        self.start()
        first = self.service.deliver_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        second = self.service.deliver_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(first.lesson.id, second.lesson.id)
        self.assertEqual(len(self.gateway.calls), 1)
        connection = self.lesson_repository.connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_lessons").fetchone()[0], 1)
            rows = connection.execute(
                "SELECT completion_token_hash FROM curriculum_lesson_deliveries"
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(len(row[0]) == 64 for row in rows))
            serialized = " ".join(row[0] for row in rows)
            self.assertNotIn(first.delivery_token, serialized)
            self.assertNotIn(second.delivery_token, serialized)
        finally:
            connection.close()

    def test_completion_is_atomic_idempotent_and_does_not_award_xp(self):
        started = self.start()
        delivery = self.service.deliver_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        first = self.service.complete_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
            delivery_token=delivery.delivery_token,
        )
        second = self.service.complete_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
            delivery_token=delivery.delivery_token,
        )
        self.assertEqual(first.progress.state, CurriculumUnitState.ASSESSMENT_REQUIRED)
        self.assertFalse(first.idempotent)
        self.assertTrue(second.idempotent)
        self.assertEqual(started.xp_awarded, first.progress.xp_awarded)
        self.assertIsNone(first.progress.mastery_score)
        connection = self.lesson_repository.connect()
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT xp FROM user_subject_progress WHERE user_id = 1 AND subject = 'math'"
                ).fetchone()[0],
                15,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM curriculum_progress_events WHERE event_type = 'curriculum_unit_lesson_completed'"
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()

    def test_parallel_generation_is_coalesced_and_parallel_completion_is_safe(self):
        self.start()
        with ThreadPoolExecutor(max_workers=4) as pool:
            deliveries = list(pool.map(
                lambda _: self.service.deliver_lesson(
                    user_id=1,
                    curriculum_unit_id=self.unit_id,
                    subject="math",
                ),
                range(4),
            ))
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(len({item.lesson.id for item in deliveries}), 1)
        token = deliveries[0].delivery_token
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: self.service.complete_lesson(
                    user_id=1,
                    curriculum_unit_id=self.unit_id,
                    subject="math",
                    delivery_token=token,
                ),
                range(2),
            ))
        self.assertEqual({item.progress.state for item in results}, {CurriculumUnitState.ASSESSMENT_REQUIRED})
        self.assertEqual(sorted(item.idempotent for item in results), [False, True])

    def test_completion_rejects_wrong_owner_unit_subject_and_tampering(self):
        self.start()
        delivery = self.service.deliver_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        with self.assertRaises(CurriculumLessonOwnershipError):
            self.service.complete_lesson(
                user_id=2,
                curriculum_unit_id=self.unit_id,
                subject="math",
                delivery_token=delivery.delivery_token,
            )
        with self.assertRaises(CurriculumLessonDeliveryInvalid):
            self.service.complete_lesson(
                user_id=1,
                curriculum_unit_id="another-unit",
                subject="math",
                delivery_token=delivery.delivery_token,
            )
        with self.assertRaises(CurriculumLessonNotAvailable):
            self.service.complete_lesson(
                user_id=1,
                curriculum_unit_id=self.unit_id,
                subject="english",
                delivery_token=delivery.delivery_token,
            )
        connection = self.lesson_repository.connect()
        connection.execute(
            "UPDATE curriculum_lessons SET content_json = '{}' WHERE id = ?",
            (delivery.lesson.id,),
        )
        connection.commit()
        connection.close()
        with self.assertRaises(CurriculumLessonConflict):
            self.service.complete_lesson(
                user_id=1,
                curriculum_unit_id=self.unit_id,
                subject="math",
                delivery_token=delivery.delivery_token,
            )
        self.assertEqual(self.progress().state, CurriculumUnitState.IN_PROGRESS)

    def test_delivery_failure_rolls_back_progress_completion(self):
        self.start()
        delivery = self.service.deliver_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        connection = self.lesson_repository.connect()
        connection.execute(
            """
            CREATE TRIGGER reject_lesson_delivery_completion
            BEFORE UPDATE OF completed_at ON curriculum_lesson_deliveries
            WHEN NEW.completed_at IS NOT NULL
            BEGIN SELECT RAISE(ABORT, 'forced delivery failure'); END
            """
        )
        connection.commit()
        connection.close()
        with self.assertRaises(CurriculumLessonPersistenceError):
            self.service.complete_lesson(
                user_id=1,
                curriculum_unit_id=self.unit_id,
                subject="math",
                delivery_token=delivery.delivery_token,
            )
        self.assertEqual(self.progress().state, CurriculumUnitState.IN_PROGRESS)
        connection = self.lesson_repository.connect()
        try:
            self.assertIsNone(connection.execute(
                "SELECT completed_at FROM curriculum_lesson_deliveries"
            ).fetchone()[0])
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_progress_events WHERE event_type = 'curriculum_unit_lesson_completed'"
            ).fetchone()[0], 0)
        finally:
            connection.close()

    def test_generation_failure_returns_503_contract_and_persists_no_lesson(self):
        self.start()
        failing_gateway = FakeGateway(
            AIResult("", "error", "limited", error_code="rate_limit", retryable=True)
        )
        service = CurriculumLessonService(
            self.lesson_repository,
            LessonEngine(AIOrchestrator(_gateway=failing_gateway)),
            self.progress_service,
            logger=self.service.logger,
        )
        with self.assertRaises(CurriculumLessonGenerationUnavailable) as captured:
            service.deliver_lesson(
                user_id=1,
                curriculum_unit_id=self.unit_id,
                subject="math",
            )
        self.assertEqual(captured.exception.http_status, 503)
        connection = self.lesson_repository.connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_lessons").fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM curriculum_lesson_events WHERE event_type = 'lesson_generation_failed'"
            ).fetchone()[0], 1)
        finally:
            connection.close()

    def test_schema_constraints_and_integrity(self):
        connection = self.lesson_repository.connect()
        try:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            indexes = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
            self.assertIn("idx_curriculum_lessons_lookup", indexes)
            self.assertIn("idx_curriculum_lesson_delivery_lookup", indexes)
        finally:
            connection.close()


class CurriculumLessonApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_security import app_module

        cls.app_module = app_module

    def setUp(self):
        self.app_module.app.config.update(TESTING=True)
        self.client = self.app_module.app.test_client()
        marker = uuid.uuid4().hex
        connection = self.app_module.get_db_connection()
        self.user_id = int(connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Lesson API", f"lesson-{marker}@example.com", "unused"),
        ).lastrowid)
        connection.execute(
            "INSERT INTO user_plans (user_id, subject) VALUES (?, 'math')",
            (self.user_id,),
        )
        connection.execute(
            "INSERT INTO user_subject_progress (user_id, subject, xp) VALUES (?, 'math', 9)",
            (self.user_id,),
        )
        self.curriculum_id = f"lesson-api-curriculum-{marker}"
        self.unit_id = f"lesson-api-unit-{marker}"
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
            user_session["user_name"] = "Lesson API"
            user_session["subject"] = "math"
            user_session["goal"] = "170"
            user_session["time_left"] = "3-plus"
            user_session["_csrf_token"] = marker
        self.csrf_token = marker

    def start_unit(self):
        return self.app_module.curriculum_progress_service.start_curriculum_unit(
            user_id=self.user_id,
            curriculum_id=self.curriculum_id,
            curriculum_unit_id=self.unit_id,
        )

    def test_auth_csrf_payload_and_completion_route(self):
        unauthenticated = self.app_module.app.test_client()
        self.assertEqual(
            unauthenticated.get(f"/api/curriculum/units/{self.unit_id}/lesson").status_code,
            401,
        )
        self.start_unit()
        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        original_gateway = self.app_module.ai_orchestrator._gateway
        self.app_module.ai_orchestrator._gateway = gateway
        try:
            delivered = self.client.get(
                f"/api/curriculum/units/{self.unit_id}/lesson"
            )
        finally:
            self.app_module.ai_orchestrator._gateway = original_gateway
        self.assertEqual(delivered.status_code, 200)
        payload = delivered.get_json()
        self.assertEqual(payload["lesson"]["section_order"], list(LESSON_SECTION_ORDER))
        self.assertNotIn("generation_metadata", payload["lesson"])
        token = payload["delivery_token"]

        endpoint = f"/api/curriculum/units/{self.unit_id}/lesson-complete"
        self.assertEqual(self.client.post(endpoint, json={"delivery_token": token}).status_code, 400)
        rejected = self.client.post(
            endpoint,
            json={"delivery_token": token, "xp": 9999, "state": "completed"},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post(
            endpoint,
            json={"delivery_token": token},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(
            accepted.get_json()["completion"]["progress"]["state"],
            "assessment_required",
        )
        repeated = self.client.post(
            endpoint,
            json={"delivery_token": token},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.get_json()["completion"]["idempotent"])

    def test_html_route_renders_structured_sections_without_legacy_breakage(self):
        self.start_unit()
        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        original_gateway = self.app_module.ai_orchestrator._gateway
        self.app_module.ai_orchestrator._gateway = gateway
        try:
            response = self.client.get(f"/curriculum/units/{self.unit_id}/lesson")
        finally:
            self.app_module.ai_orchestrator._gateway = original_gateway
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("1. Навчальна мета", html)
        self.assertIn("9. Перехід до перевірки", html)
        self.assertIn("delivery_token", html)
        self.assertEqual(self.client.get("/lesson/1").status_code, 200)

    def test_dashboard_starts_available_unit_then_opens_production_lesson(self):
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        start_path = f"/curriculum/units/{self.unit_id}/start"
        self.assertIn(f'action="{start_path}"', html)
        self.assertNotIn('href="/lesson/1"', html)

        self.assertEqual(self.client.post(start_path).status_code, 400)
        started = self.client.post(
            start_path,
            data={"_csrf_token": self.csrf_token},
        )
        self.assertEqual(started.status_code, 302)
        lesson_path = f"/curriculum/units/{self.unit_id}/lesson"
        self.assertTrue(started.headers["Location"].endswith(lesson_path))

        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        original_gateway = self.app_module.ai_orchestrator._gateway
        self.app_module.ai_orchestrator._gateway = gateway
        try:
            lesson = self.client.get(lesson_path)
        finally:
            self.app_module.ai_orchestrator._gateway = original_gateway
        self.assertEqual(lesson.status_code, 200)
        self.assertIn("9. Перехід до перевірки", lesson.get_data(as_text=True))

    def test_all_active_navigation_surfaces_use_curriculum_unit_urls(self):
        self.start_unit()
        production_path = f"/curriculum/units/{self.unit_id}/lesson"
        for path in ("/dashboard", "/today", "/library", "/planner"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn(production_path, html)
                self.assertNotIn('href="/lesson/1"', html)

    def test_production_navigation_calls_delivery_service_and_passes_typed_lesson(self):
        self.start_unit()
        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        original_gateway = self.app_module.ai_orchestrator._gateway
        self.app_module.ai_orchestrator._gateway = gateway
        rendered = []

        def record_template(_sender, template, context, **_extra):
            rendered.append((template, context))

        template_rendered.connect(record_template, self.app_module.app)
        lesson_path = f"/curriculum/units/{self.unit_id}/lesson"
        try:
            with (
                patch.object(
                    self.app_module.curriculum_lesson_service,
                    "deliver_lesson",
                    wraps=self.app_module.curriculum_lesson_service.deliver_lesson,
                ) as deliver,
                patch.object(
                    self.app_module,
                    "get_lesson_content",
                    side_effect=AssertionError("legacy lesson fallback was used"),
                ),
                patch.object(
                    self.app_module,
                    "get_lesson_details",
                    side_effect=AssertionError("legacy lesson details were used"),
                ),
            ):
                response = self.client.get(lesson_path)
        finally:
            template_rendered.disconnect(record_template, self.app_module.app)
            self.app_module.ai_orchestrator._gateway = original_gateway

        self.assertEqual(response.status_code, 200)
        deliver.assert_called_once_with(
            user_id=self.user_id,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        self.assertEqual(rendered[-1][0].name, "curriculum_lesson.html")
        lesson = rendered[-1][1]["production_lesson"]
        self.assertEqual(lesson.section_order, LESSON_SECTION_ORDER)
        self.assertEqual(lesson.curriculum_unit_id, self.unit_id)

    def test_refresh_uses_cached_lesson_and_html_completion_is_idempotent(self):
        self.start_unit()
        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        original_gateway = self.app_module.ai_orchestrator._gateway
        self.app_module.ai_orchestrator._gateway = gateway
        rendered = []

        def record_template(_sender, template, context, **_extra):
            if template.name == "curriculum_lesson.html":
                rendered.append(context)

        template_rendered.connect(record_template, self.app_module.app)
        lesson_path = f"/curriculum/units/{self.unit_id}/lesson"
        completion_path = f"/curriculum/units/{self.unit_id}/lesson-complete"
        try:
            first = self.client.get(lesson_path)
            second = self.client.get(lesson_path)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(len(gateway.calls), 1)
            self.assertEqual(
                rendered[0]["production_lesson"].id,
                rendered[1]["production_lesson"].id,
            )
            self.assertFalse(rendered[0]["lesson_cached"])
            self.assertTrue(rendered[1]["lesson_cached"])
            delivery_token = rendered[0]["lesson_delivery_token"]
            self.assertTrue(delivery_token)

            completion_form = {
                "_csrf_token": self.csrf_token,
                "delivery_token": delivery_token,
            }
            completed = self.client.post(
                completion_path,
                data=completion_form,
                follow_redirects=True,
            )
            repeated = self.client.post(
                completion_path,
                data=completion_form,
                follow_redirects=True,
            )
        finally:
            template_rendered.disconnect(record_template, self.app_module.app)
            self.app_module.ai_orchestrator._gateway = original_gateway

        self.assertEqual(completed.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(len(gateway.calls), 1)
        snapshot = self.app_module.curriculum_progress_service.get_active_curriculum_progress(
            user_id=self.user_id,
            subject="math",
        )
        self.assertEqual(snapshot.units[0].state, CurriculumUnitState.ASSESSMENT_REQUIRED)

    def test_unauthorized_navigation_cannot_start_or_open_curriculum_unit(self):
        unauthenticated = self.app_module.app.test_client()
        self.assertEqual(
            unauthenticated.get(
                f"/curriculum/units/{self.unit_id}/lesson"
            ).status_code,
            302,
        )
        self.assertEqual(
            unauthenticated.post(
                f"/curriculum/units/{self.unit_id}/start"
            ).status_code,
            400,
        )

        marker = uuid.uuid4().hex
        connection = self.app_module.get_db_connection()
        other_user_id = int(connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other learner", f"other-lesson-{marker}@example.com", "unused"),
        ).lastrowid)
        connection.execute(
            "INSERT INTO user_plans (user_id, subject) VALUES (?, 'math')",
            (other_user_id,),
        )
        connection.commit()
        connection.close()
        other_client = self.app_module.app.test_client()
        with other_client.session_transaction() as other_session:
            other_session["user_id"] = other_user_id
            other_session["subject"] = "math"
            other_session["goal"] = "170"
            other_session["time_left"] = "3-plus"
            other_session["_csrf_token"] = marker
        self.assertEqual(
            other_client.get(
                f"/curriculum/units/{self.unit_id}/lesson"
            ).status_code,
            403,
        )
        self.assertEqual(
            other_client.post(
                f"/curriculum/units/{self.unit_id}/start",
                data={"_csrf_token": marker},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
