from pathlib import Path
import sqlite3
import unittest
import uuid

from tests.test_security import app_module


class Beta2XpRepairTests(unittest.TestCase):
    def create_user(self, *, subject="english", xp=0):
        email = f"beta2-{uuid.uuid4().hex}@example.com"
        with sqlite3.connect(app_module.DB_PATH) as connection:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Beta Two", email, "test"),
            )
            user_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO user_plans
                    (user_id, goal, subject, time_left, progress, xp, streak, diagnostic_required)
                VALUES (?, '200', ?, '3-plus', 8, ?, 1, 0)
                """,
                (user_id, subject, xp),
            )
            connection.execute(
                """
                INSERT INTO user_subject_progress (user_id, subject, progress, xp, streak)
                VALUES (?, ?, 8, ?, 1)
                """,
                (user_id, subject, xp),
            )
        return user_id

    def test_completed_lesson_with_stale_zero_mirror_is_repaired(self):
        user_id = self.create_user(xp=0)
        with sqlite3.connect(app_module.DB_PATH) as connection:
            connection.execute(
                """
                INSERT INTO completed_lessons
                    (user_id, subject, lesson_id, best_score, total)
                VALUES (?, 'english', 1, 20, 24)
                """,
                (user_id,),
            )
            connection.execute(
                """
                INSERT INTO quiz_attempts
                    (attempt_token, user_id, subject, lesson_id, score, total,
                     passed, xp_awarded, review_json, finalized_at)
                VALUES (?, ?, 'english', 1, 20, 24, 1, 60, '[]', CURRENT_TIMESTAMP)
                """,
                (f"attempt-{uuid.uuid4().hex}", user_id),
            )

        repaired = app_module.reconcile_subject_xp(user_id, "english")
        self.assertEqual(repaired, 60)
        with sqlite3.connect(app_module.DB_PATH) as connection:
            subject_xp = connection.execute(
                "SELECT xp FROM user_subject_progress WHERE user_id = ? AND subject = 'english'",
                (user_id,),
            ).fetchone()[0]
            plan_xp = connection.execute(
                "SELECT xp FROM user_plans WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
        self.assertEqual((subject_xp, plan_xp), (60, 60))

    def test_repair_never_reduces_or_duplicates_existing_xp(self):
        user_id = self.create_user(xp=75)
        with sqlite3.connect(app_module.DB_PATH) as connection:
            connection.execute(
                """
                INSERT INTO completed_lessons
                    (user_id, subject, lesson_id, best_score, total)
                VALUES (?, 'english', 1, 20, 24)
                """,
                (user_id,),
            )
        self.assertEqual(app_module.reconcile_subject_xp(user_id, "english"), 75)
        self.assertEqual(app_module.reconcile_subject_xp(user_id, "english"), 75)


class Beta2MobileUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_mobile_primary_lesson_cta_spans_the_card(self):
        template = (self.root / "templates" / "dashboard.html").read_text(encoding="utf-8")
        css = (self.root / "static" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("dashboard-primary-lesson-cta", template)
        self.assertIn("grid-column: 1 / -1", css)
        self.assertIn("min-height: 52px", css)
        self.assertIn("dashboard-clean-hero-visual", css)
        self.assertIn("display: none", css)

    def test_today_route_shows_only_nearby_topics_and_links_to_full_library(self):
        template = (self.root / "templates" / "today.html").read_text(encoding="utf-8")
        self.assertIn("curriculum_navigation.nearby_units", template)
        self.assertIn("dashboard_lessons", template)
        self.assertIn("Інші уроки", template)
        self.assertIn("url_for('library')", template)


if __name__ == "__main__":
    unittest.main()
