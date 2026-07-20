import json
import logging
import sqlite3
import tempfile
import unittest

from easynmt_ai import AIOrchestrator, LessonEngine
from easynmt_ai.curriculum import CurriculumRepository
from easynmt_core.lessons import CurriculumLessonRepository, CurriculumLessonService
from easynmt_core.progress import CurriculumProgressRepository, CurriculumProgressService, CurriculumUnitState
from easynmt_core.quizzes import (
    CurriculumQuizNotAvailable,
    CurriculumQuizOwnershipError,
    CurriculumQuizRepository,
    CurriculumQuizService,
    build_deterministic_quiz,
)
from tests.lesson_fixtures import valid_lesson_proposal
from tests.test_curriculum_progress import insert_curriculum_rows
from tests.test_lesson_engine import FakeGateway, ai_response


class ProductionQuizServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/quiz.db"
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
        self.curriculum_id = "curriculum-quiz"
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
        logger = logging.getLogger(f"tests.quiz.production.{id(self)}")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        self.lesson_service = CurriculumLessonService(
            self.lesson_repository,
            LessonEngine(AIOrchestrator(_gateway=FakeGateway(
                ai_response(valid_lesson_proposal(competency_count=2))
            ))),
            self.progress_service,
            logger=logger,
        )
        self.quiz_repository = CurriculumQuizRepository(self.db_path)
        self.quiz_repository.ensure_schema()
        self.quiz_service = CurriculumQuizService(
            self.quiz_repository,
            self.progress_service,
            logger=logger,
        )

        self.progress_service.start_curriculum_unit(
            user_id=1,
            curriculum_id=self.curriculum_id,
            curriculum_unit_id=self.unit_id,
        )
        delivery = self.lesson_service.deliver_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
        )
        self.lesson = delivery.lesson
        self.delivery_token = delivery.delivery_token

    def tearDown(self):
        self.temp_dir.cleanup()

    def complete_lesson(self):
        return self.lesson_service.complete_lesson(
            user_id=1,
            curriculum_unit_id=self.unit_id,
            subject="math",
            delivery_token=self.delivery_token,
        )

    def correct_answers(self, attempt):
        return {question.id: question.correct_answer for question in attempt.quiz.questions}

    def progress(self):
        return self.progress_service.get_curriculum_progress(
            user_id=1,
            curriculum_id=self.curriculum_id,
        ).units[0]

    def test_quiz_contract_is_exactly_twelve_questions_and_twenty_four_points(self):
        quiz = build_deterministic_quiz(self.lesson)
        self.assertEqual(len(quiz.questions), 12)
        self.assertEqual([q.points for q in quiz.questions], [1] * 4 + [2] * 4 + [3] * 4)
        self.assertEqual(quiz.max_score, 24)
        self.assertEqual(quiz.pass_score, 18)
        public = quiz.to_public_dict()
        self.assertNotIn("correct_answer", public["questions"][0])
        self.assertNotIn("keywords", public["questions"][4])

    def test_quiz_cannot_start_before_lesson_completion(self):
        with self.assertRaises(CurriculumQuizNotAvailable):
            self.quiz_service.start_attempt(
                user_id=1,
                subject="math",
                lesson=self.lesson,
            )

    def test_pass_is_atomic_unlocks_progress_and_awards_xp_once(self):
        self.complete_lesson()
        attempt = self.quiz_service.start_attempt(
            user_id=1,
            subject="math",
            lesson=self.lesson,
        )
        result = self.quiz_service.submit_attempt(
            user_id=1,
            subject="math",
            curriculum_unit_id=self.unit_id,
            attempt_token=attempt.attempt_token,
            answers=self.correct_answers(attempt),
        )
        self.assertEqual(result.score, 24)
        self.assertTrue(result.passed)
        self.assertEqual(result.xp_awarded, 60)
        self.assertEqual(self.progress().state, CurriculumUnitState.COMPLETED)
        connection = self.quiz_repository.connect()
        try:
            self.assertEqual(connection.execute(
                "SELECT xp_awarded FROM curriculum_unit_progress WHERE user_id = 1 AND curriculum_unit_id = ?",
                (self.unit_id,),
            ).fetchone()[0], 60)
        finally:
            connection.close()
        connection = self.quiz_repository.connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_quiz_attempts").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_assessment_results").fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT xp FROM user_subject_progress WHERE user_id = 1 AND subject = 'math'"
            ).fetchone()[0], 75)
        finally:
            connection.close()

        duplicate = self.quiz_service.submit_attempt(
            user_id=1,
            subject="math",
            curriculum_unit_id=self.unit_id,
            attempt_token=attempt.attempt_token,
            answers={},
        )
        self.assertTrue(duplicate.idempotent)
        connection = self.quiz_repository.connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_quiz_attempts").fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT xp FROM user_subject_progress WHERE user_id = 1 AND subject = 'math'"
            ).fetchone()[0], 75)
        finally:
            connection.close()

    def test_client_cannot_inflate_score_with_unknown_or_repeated_fields(self):
        self.complete_lesson()
        attempt = self.quiz_service.start_attempt(user_id=1, subject="math", lesson=self.lesson)
        first = attempt.quiz.questions[0]
        forged = {
            first.id: first.correct_answer,
            "fake-question": "correct",
            "score": "24",
            "passed": "true",
            "xp": "99999",
        }
        result = self.quiz_service.submit_attempt(
            user_id=1,
            subject="math",
            curriculum_unit_id=self.unit_id,
            attempt_token=attempt.attempt_token,
            answers=forged,
        )
        self.assertEqual(result.score, 1)
        self.assertFalse(result.passed)
        self.assertEqual(result.xp_awarded, 0)
        self.assertEqual(self.progress().state, CurriculumUnitState.ASSESSMENT_REQUIRED)

    def test_attempt_owner_and_unit_are_server_scoped(self):
        self.complete_lesson()
        attempt = self.quiz_service.start_attempt(user_id=1, subject="math", lesson=self.lesson)
        with self.assertRaises(CurriculumQuizOwnershipError):
            self.quiz_service.submit_attempt(
                user_id=2,
                subject="math",
                curriculum_unit_id=self.unit_id,
                attempt_token=attempt.attempt_token,
                answers={},
            )

    def test_attempt_and_progress_roll_back_together(self):
        self.complete_lesson()
        attempt = self.quiz_service.start_attempt(user_id=1, subject="math", lesson=self.lesson)
        connection = self.quiz_repository.connect()
        connection.execute(
            """
            CREATE TRIGGER reject_production_quiz_attempt
            BEFORE INSERT ON curriculum_quiz_attempts
            BEGIN SELECT RAISE(ABORT, 'forced attempt failure'); END
            """
        )
        connection.commit()
        connection.close()

        with self.assertRaises(sqlite3.IntegrityError):
            self.quiz_service.submit_attempt(
                user_id=1,
                subject="math",
                curriculum_unit_id=self.unit_id,
                attempt_token=attempt.attempt_token,
                answers=self.correct_answers(attempt),
            )
        self.assertEqual(self.progress().state, CurriculumUnitState.ASSESSMENT_REQUIRED)
        connection = self.quiz_repository.connect()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_quiz_attempts").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM curriculum_assessment_results").fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT xp FROM user_subject_progress WHERE user_id = 1 AND subject = 'math'"
            ).fetchone()[0], 15)
        finally:
            connection.close()

    def test_draft_accepts_only_server_question_ids(self):
        self.complete_lesson()
        attempt = self.quiz_service.start_attempt(user_id=1, subject="math", lesson=self.lesson)
        first = attempt.quiz.questions[0]
        self.quiz_service.save_draft(
            user_id=1,
            subject="math",
            curriculum_unit_id=self.unit_id,
            answers={first.id: "saved", "forged": "ignored"},
        )
        connection = self.quiz_repository.connect()
        try:
            raw = connection.execute("SELECT answers_json FROM curriculum_quiz_drafts").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(json.loads(raw), {first.id: "saved"})


if __name__ == "__main__":
    unittest.main()


class ProductionQuizApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_security import app_module
        cls.app_module = app_module

    def setUp(self):
        import uuid
        from werkzeug.security import generate_password_hash

        self.app_module.app.config.update(TESTING=True)
        self.client = self.app_module.app.test_client()
        marker = uuid.uuid4().hex
        connection = self.app_module.get_db_connection()
        self.user_id = int(connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Quiz API", f"quiz-api-{marker}@example.com", generate_password_hash("unused-password")),
        ).lastrowid)
        connection.execute(
            "INSERT INTO user_plans (user_id, goal, subject, time_left) VALUES (?, '170', 'math', '3-plus')",
            (self.user_id,),
        )
        connection.execute(
            "INSERT INTO user_subject_progress (user_id, subject, xp) VALUES (?, 'math', 0)",
            (self.user_id,),
        )
        self.curriculum_id = f"quiz-api-curriculum-{marker}"
        self.unit_id = f"quiz-api-unit-{marker}"
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
            user_session["user_name"] = "Quiz API"
            user_session["subject"] = "math"
            user_session["goal"] = "170"
            user_session["time_left"] = "3-plus"
            user_session["_csrf_token"] = marker
        self.csrf = marker

    def prepare_assessment(self):
        self.app_module.curriculum_progress_service.start_curriculum_unit(
            user_id=self.user_id,
            curriculum_id=self.curriculum_id,
            curriculum_unit_id=self.unit_id,
        )
        gateway = FakeGateway(ai_response(valid_lesson_proposal(competency_count=2)))
        original_gateway = self.app_module.ai_orchestrator._gateway
        self.app_module.ai_orchestrator._gateway = gateway
        try:
            lesson = self.client.get(f"/api/curriculum/units/{self.unit_id}/lesson")
        finally:
            self.app_module.ai_orchestrator._gateway = original_gateway
        self.assertEqual(lesson.status_code, 200)
        token = lesson.get_json()["delivery_token"]
        completed = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/lesson-complete",
            json={"delivery_token": token},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(completed.status_code, 200)

    def test_api_hides_answer_key_and_finalizes_server_snapshot(self):
        self.prepare_assessment()
        started = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/quiz/start",
            json={},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(started.status_code, 200)
        payload = started.get_json()["attempt"]
        self.assertEqual(len(payload["quiz"]["questions"]), 12)
        self.assertNotIn("correct_answer", payload["quiz"]["questions"][0])
        attempt_token = payload["attempt_token"]
        connection = self.app_module.get_db_connection()
        row = connection.execute(
            "SELECT quiz_snapshot_json FROM curriculum_quiz_sessions WHERE attempt_token = ?",
            (attempt_token,),
        ).fetchone()
        connection.close()
        snapshot = json.loads(row["quiz_snapshot_json"])
        answers = {item["id"]: item["correct_answer"] for item in snapshot["questions"]}
        submitted = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/quiz/submit",
            json={"attempt_token": attempt_token, "answers": answers},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(submitted.status_code, 200)
        attempt = submitted.get_json()["attempt"]
        self.assertEqual(attempt["score"], 24)
        self.assertTrue(attempt["passed"])
        repeated = self.client.post(
            f"/api/curriculum/units/{self.unit_id}/quiz/submit",
            json={"attempt_token": attempt_token, "answers": {}},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.get_json()["attempt"]["idempotent"])

    def test_html_quiz_and_result_routes_render(self):
        self.prepare_assessment()
        page = self.client.get(f"/curriculum/units/{self.unit_id}/quiz")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("12 питань", html)
        self.assertIn("Завершити тест", html)
        self.assertNotIn("correct_answer", html)
