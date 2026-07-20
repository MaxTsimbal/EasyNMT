import logging
import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from easynmt_ai import ACTIVE_SUBJECT_KEYS, AIOrchestrator, CurriculumEngine
from easynmt_ai.curriculum import (
    CurriculumRepository,
    CurriculumService,
    load_taxonomy,
)
from easynmt_core.curriculum_bootstrap import (
    CurriculumBootstrapError,
    DevelopmentCurriculumBootstrapService,
)
from easynmt_core.progress import CurriculumProgressRepository, CurriculumProgressService


class DevelopmentCurriculumBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name, "users.db"))
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE user_plans (
                user_id INTEGER PRIMARY KEY,
                goal TEXT,
                subject TEXT,
                time_left TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE completed_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                lesson_id INTEGER NOT NULL,
                best_score INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, subject, lesson_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE user_subject_progress (
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                PRIMARY KEY(user_id, subject),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE diagnostic_results (
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                level TEXT NOT NULL,
                PRIMARY KEY(user_id, subject),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            INSERT INTO users (id, name) VALUES (1, 'Existing learner');
            INSERT INTO user_plans
                (user_id, goal, subject, time_left, progress, xp)
            VALUES (1, '170', 'english', '3-plus', 37, 44);
            INSERT INTO user_subject_progress
                (user_id, subject, progress, xp, streak)
            VALUES (1, 'math', 12, 73, 2);
            INSERT INTO completed_lessons
                (user_id, subject, lesson_id, best_score, total)
            VALUES (1, 'math', 1, 9, 10);
            """
        )
        connection.commit()
        connection.close()

        self.curriculum_repository = CurriculumRepository(self.db_path)
        self.curriculum_repository.ensure_schema()
        self.progress_repository = CurriculumProgressRepository(self.db_path)
        self.progress_repository.ensure_schema()
        self.progress_service = CurriculumProgressService(self.progress_repository)
        logger = logging.getLogger(f"tests.curriculum.bootstrap.{id(self)}")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        orchestrator = AIOrchestrator(settings={}, logger=logger)
        self.curriculum_services = {}
        for subject in ACTIVE_SUBJECT_KEYS:
            engine = CurriculumEngine(
                orchestrator,
                taxonomy=load_taxonomy(subject),
            )
            self.curriculum_services[subject] = CurriculumService(
                engine,
                self.curriculum_repository,
                progress_service=self.progress_service,
            )
        self.curriculum_service = self.curriculum_services["math"]
        self.bootstrap_service = DevelopmentCurriculumBootstrapService(
            self.db_path,
            self.curriculum_service,
            self.curriculum_repository,
            curriculum_services=self.curriculum_services,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def counts(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return {
                "users": connection.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "curricula": connection.execute(
                    "SELECT COUNT(*) FROM ai_curricula"
                ).fetchone()[0],
                "units": connection.execute(
                    "SELECT COUNT(*) FROM ai_curriculum_units"
                ).fetchone()[0],
                "progress": connection.execute(
                    "SELECT COUNT(*) FROM curriculum_unit_progress"
                ).fetchone()[0],
                "xp": connection.execute(
                    """
                    SELECT xp FROM user_subject_progress
                    WHERE user_id = 1 AND subject = 'math'
                    """
                ).fetchone()[0],
                "legacy": connection.execute(
                    "SELECT COUNT(*) FROM completed_lessons WHERE user_id = 1"
                ).fetchone()[0],
            }
        finally:
            connection.close()

    def test_bootstrap_publishes_idempotently_and_preserves_existing_data(self):
        before = self.counts()
        first = self.bootstrap_service.bootstrap()
        after_first = self.counts()
        second = self.bootstrap_service.bootstrap()
        after_second = self.counts()

        self.assertEqual(first.created, 1)
        self.assertEqual(first.users[0].action, "created")
        self.assertTrue(first.users[0].published)
        self.assertGreaterEqual(len(first.users[0].unit_ids), 4)
        self.assertEqual(second.reused, 1)
        self.assertEqual(second.users[0].curriculum_id, first.users[0].curriculum_id)
        self.assertEqual(after_first, after_second)
        self.assertEqual(after_first["users"], before["users"])
        self.assertEqual(after_first["curricula"], 1)
        self.assertEqual(after_first["units"], after_first["progress"])
        self.assertEqual(after_first["xp"], before["xp"])
        self.assertEqual(after_first["legacy"], before["legacy"])

        status = self.bootstrap_service.status()
        self.assertEqual(status.database_target, str(Path(self.db_path).resolve()))
        self.assertEqual(status.published_curricula_count, 1)
        self.assertEqual(status.mathematics[0]["status"], "published")


    def test_all_subject_bootstrap_is_idempotent_and_subject_isolated(self):
        before = self.counts()
        first = self.bootstrap_service.bootstrap(all_subjects=True)
        after_first = self.counts()
        second = self.bootstrap_service.bootstrap(all_subjects=True)
        after_second = self.counts()

        self.assertEqual(set(first.subjects), set(ACTIVE_SUBJECT_KEYS))
        self.assertEqual(first.created, len(ACTIVE_SUBJECT_KEYS))
        self.assertEqual(second.reused, len(ACTIVE_SUBJECT_KEYS))
        self.assertEqual(after_first, after_second)
        self.assertEqual(after_first["users"], before["users"])
        self.assertEqual(after_first["xp"], before["xp"])
        self.assertEqual(after_first["legacy"], before["legacy"])

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT c.subject, c.status, COUNT(DISTINCT u.unit_id) AS units,
                       COUNT(DISTINCT p.id) AS progress
                FROM ai_curricula c
                JOIN ai_curriculum_units u ON u.curriculum_id = c.id
                JOIN curriculum_unit_progress p
                  ON p.curriculum_id = c.id AND p.user_id = c.user_id
                WHERE c.user_id = 1
                GROUP BY c.subject, c.status
                ORDER BY c.subject
                """
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual({row["subject"] for row in rows}, set(ACTIVE_SUBJECT_KEYS))
        self.assertTrue(all(row["status"] == "published" for row in rows))
        self.assertTrue(all(int(row["units"]) == int(row["progress"]) for row in rows))

        status = self.bootstrap_service.status()
        self.assertEqual(
            {item["subject"] for item in status.subjects},
            set(ACTIVE_SUBJECT_KEYS),
        )

    def test_missing_baseline_unit_and_progress_are_repaired_without_duplicates(self):
        initial = self.bootstrap_service.bootstrap().users[0]
        snapshot_before = self.progress_service.get_active_curriculum_progress(
            user_id=1,
            subject="math",
        )
        removed_unit_id = initial.unit_ids[-1]
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "DELETE FROM ai_curriculum_units WHERE curriculum_id = ? AND unit_id = ?",
            (initial.curriculum_id, removed_unit_id),
        )
        connection.commit()
        connection.close()

        repaired = self.bootstrap_service.bootstrap().users[0]
        snapshot_after = self.progress_service.get_active_curriculum_progress(
            user_id=1,
            subject="math",
        )
        self.assertEqual(repaired.action, "repaired")
        self.assertEqual(repaired.repaired_units, 1)
        self.assertEqual(repaired.repaired_progress_units, 1)
        self.assertEqual(snapshot_after.total_units, snapshot_before.total_units)
        self.assertEqual(
            snapshot_after.units[0].state,
            snapshot_before.units[0].state,
        )
        counts = self.counts()
        self.assertEqual(counts["curricula"], 1)
        self.assertEqual(counts["units"], snapshot_after.total_units)
        self.assertEqual(counts["progress"], snapshot_after.total_units)

    def test_production_requires_two_explicit_overrides(self):
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}, clear=False):
            os.environ.pop("EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP", None)
            with self.assertRaises(CurriculumBootstrapError):
                self.bootstrap_service.bootstrap(allow_production=True)
            with patch.dict(
                os.environ,
                {"EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP": "1"},
                clear=False,
            ):
                report = self.bootstrap_service.bootstrap(allow_production=True)
        self.assertTrue(report.users[0].published)


class CurriculumBootstrapCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_security import app_module

        cls.app_module = app_module

    def test_status_and_bootstrap_use_the_application_database(self):
        runner = self.app_module.app.test_cli_runner()
        status = runner.invoke(args=["curriculum", "status"])
        self.assertEqual(status.exit_code, 0, status.output)
        self.assertIn(
            f"database_target={Path(self.app_module.DB_PATH).resolve()}",
            status.output,
        )

        marker = uuid.uuid4().hex
        connection = self.app_module.get_db_connection()
        user_id = int(connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Bootstrap CLI", f"bootstrap-{marker}@example.com", "unused"),
        ).lastrowid)
        connection.execute(
            """
            INSERT INTO user_plans (user_id, goal, subject, time_left)
            VALUES (?, '170', 'math', '3-plus')
            """,
            (user_id,),
        )
        connection.commit()
        connection.close()

        result = runner.invoke(
            args=["curriculum", "bootstrap-development", "--user-id", str(user_id)]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(f"user={user_id} action=created", result.output)
        active = self.app_module.curriculum_service.get_active_curriculum(
            user_id=user_id,
            subject="math",
        )
        self.assertIsNotNone(active)
        self.assertEqual(active.status.value, "published")

        client = self.app_module.app.test_client()
        with client.session_transaction() as user_session:
            user_session["user_id"] = user_id
            user_session["user_name"] = "Bootstrap CLI"
            user_session["subject"] = "math"
            user_session["goal"] = "170"
            user_session["time_left"] = "3-plus"
        dashboard = client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        html = dashboard.get_data(as_text=True)
        self.assertIn(
            f'/curriculum/units/{active.units[0].id}/start',
            html,
        )
        self.assertNotIn('href="/lesson/', html)
        self.assertNotIn('action="/lesson/', html)


    def test_all_subject_cli_routes_every_active_dashboard_to_production(self):
        runner = self.app_module.app.test_cli_runner()
        marker = uuid.uuid4().hex
        connection = self.app_module.get_db_connection()
        user_id = int(connection.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("All Subjects CLI", f"all-subjects-{marker}@example.com", "unused"),
        ).lastrowid)
        connection.execute(
            """
            INSERT INTO user_plans (user_id, goal, subject, time_left)
            VALUES (?, '170', 'math', '3-plus')
            """,
            (user_id,),
        )
        connection.commit()
        connection.close()

        result = runner.invoke(args=[
            "curriculum",
            "bootstrap-development",
            "--user-id",
            str(user_id),
            "--all-subjects",
        ])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(f"created={len(ACTIVE_SUBJECT_KEYS)}", result.output)

        client = self.app_module.app.test_client()
        for subject in ACTIVE_SUBJECT_KEYS:
            active = self.app_module.curriculum_services[subject].get_active_curriculum(
                user_id=user_id,
                subject=subject,
            )
            self.assertIsNotNone(active, subject)
            self.assertEqual(active.status.value, "published")
            with client.session_transaction() as user_session:
                user_session["user_id"] = user_id
                user_session["user_name"] = "All Subjects CLI"
                user_session["subject"] = subject
                user_session["goal"] = "170"
                user_session["time_left"] = "3-plus"
            dashboard = client.get("/dashboard")
            self.assertEqual(dashboard.status_code, 200, subject)
            html = dashboard.get_data(as_text=True)
            self.assertIn(
                f'/curriculum/units/{active.units[0].id}/start',
                html,
                subject,
            )
            self.assertNotIn('href="/lesson/', html, subject)
            self.assertNotIn('action="/lesson/', html, subject)

        status = runner.invoke(args=["curriculum", "status"])
        self.assertEqual(status.exit_code, 0, status.output)
        for subject in ACTIVE_SUBJECT_KEYS:
            self.assertIn(f"subject={subject} user:{user_id}", status.output)


if __name__ == "__main__":
    unittest.main()
