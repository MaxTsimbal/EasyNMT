from contextlib import closing
import json
import re
import sqlite3
import unittest
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from tests.test_security import app_module


class QuizFlowTests(unittest.TestCase):
    counter = 0

    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()
        type(self).counter += 1
        self.email = f"quiz-flow-{self.counter}@example.com"
        self.user_id = self.onboard(self.email)

    def csrf(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.get_data(as_text=True))
        self.assertIsNotNone(match, path)
        return match.group(1), response

    def onboard(self, email):
        token, _ = self.csrf("/register")
        response = self.client.post(
            "/register",
            data={
                "_csrf_token": token,
                "name": "Quiz Flow",
                "email": email,
                "password": "correct-password",
                "confirm_password": "correct-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        for page, endpoint in (
            ("/goal", "/set-goal/170"),
            ("/subject", "/set-subject/math"),
            ("/date", "/set-time/3-plus"),
        ):
            token, _ = self.csrf(page)
            self.assertEqual(
                self.client.post(endpoint, data={"_csrf_token": token}).status_code,
                302,
            )
        token, _ = self.csrf("/diagnostic")
        diagnostic_data = {
            f"q{index}": question[2]
            for index, question in enumerate(app_module.DIAGNOSTIC_BANK["math"], 1)
        }
        diagnostic_data["_csrf_token"] = token
        self.assertEqual(self.client.post("/diagnostic", data=diagnostic_data).status_code, 302)
        with self.client.session_transaction() as session:
            return int(session["user_id"])

    def open_quiz(self, lesson_id=1):
        token, _ = self.csrf(f"/lesson/{lesson_id}")
        response = self.client.post(
            f"/lesson/{lesson_id}/ready",
            data={"_csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        token, response = self.csrf(f"/quiz/{lesson_id}")
        html = response.get_data(as_text=True)
        attempt_token = re.search(r'name="attempt_token" value="([^"]+)"', html).group(1)
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            row = conn.execute(
                "SELECT quiz_json FROM quiz_sessions WHERE attempt_token = ?",
                (attempt_token,),
            ).fetchone()
        return token, attempt_token, json.loads(row[0])

    def submit_answers(self, csrf_token, attempt_token, quiz_map, *, correct=True, repeated_id=False):
        pairs = [("_csrf_token", csrf_token), ("attempt_token", attempt_token)]
        if repeated_id:
            first_id, first = next(iter(quiz_map.items()))
            pairs.extend(("question_ids", first_id) for _ in range(24))
            pairs.append((f"answer_{first_id}", first["answer"]))
        else:
            for question_id, question in quiz_map.items():
                pairs.append(("question_ids", question_id))
                if correct:
                    pairs.append((f"answer_{question_id}", question["answer"]))
        return self.client.post("/quiz/1", data=MultiDict(pairs))

    def test_client_question_ids_cannot_inflate_score(self):
        csrf_token, attempt_token, quiz_map = self.open_quiz()
        response = self.submit_answers(
            csrf_token,
            attempt_token,
            quiz_map,
            repeated_id=True,
        )
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            attempt = conn.execute(
                "SELECT score, total, passed, xp_awarded FROM quiz_attempts WHERE attempt_token = ?",
                (attempt_token,),
            ).fetchone()
            completed = conn.execute(
                "SELECT COUNT(*) FROM completed_lessons WHERE user_id = ? AND subject = 'math'",
                (self.user_id,),
            ).fetchone()[0]
        self.assertEqual(attempt, (1, 24, 0, 10))
        self.assertEqual(completed, 0)

    def test_successful_attempt_updates_all_progress_atomically_and_is_idempotent(self):
        csrf_token, attempt_token, quiz_map = self.open_quiz()
        response = self.submit_answers(csrf_token, attempt_token, quiz_map)
        self.assertEqual(response.status_code, 302)

        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            attempt = conn.execute(
                "SELECT score, total, passed, xp_awarded, finalized_at FROM quiz_attempts WHERE attempt_token = ?",
                (attempt_token,),
            ).fetchone()
            completed = conn.execute(
                "SELECT best_score, total FROM completed_lessons WHERE user_id = ? AND subject = 'math' AND lesson_id = 1",
                (self.user_id,),
            ).fetchone()
            progress = conn.execute(
                "SELECT progress, xp, last_quiz_score, last_quiz_total FROM user_subject_progress WHERE user_id = ? AND subject = 'math'",
                (self.user_id,),
            ).fetchone()
        self.assertEqual(attempt[:4], (24, 24, 1, 60))
        self.assertIsNotNone(attempt[4])
        self.assertEqual(completed, (24, 24))
        self.assertEqual(progress, (33, 60, 24, 24))
        self.assertEqual(self.client.get("/lesson/2").status_code, 200)

        duplicate = self.submit_answers(csrf_token, attempt_token, quiz_map)
        self.assertEqual(duplicate.status_code, 302)
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE attempt_token = ?", (attempt_token,)).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT xp FROM user_subject_progress WHERE user_id = ? AND subject = 'math'", (self.user_id,)).fetchone()[0],
                60,
            )

        # A stale browser session may not overwrite authoritative progress.
        with self.client.session_transaction() as session:
            session["xp"] = 0
            session["progress"] = 0
        self.assertEqual(self.client.get("/lesson/1").status_code, 200)
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            self.assertEqual(
                conn.execute("SELECT progress, xp FROM user_subject_progress WHERE user_id = ? AND subject = 'math'", (self.user_id,)).fetchone(),
                (33, 60),
            )

        logout_token, _ = self.csrf("/result")
        self.assertEqual(
            self.client.post("/logout", data={"_csrf_token": logout_token}).status_code,
            302,
        )
        login_token, _ = self.csrf("/login")
        self.assertEqual(
            self.client.post(
                "/login",
                data={
                    "_csrf_token": login_token,
                    "email": self.email,
                    "password": "correct-password",
                },
            ).status_code,
            302,
        )
        with self.client.session_transaction() as session:
            self.assertEqual(session["xp"], 60)
            self.assertEqual(session["progress"], 33)

    def test_failed_then_passed_attempt_caps_total_lesson_xp_at_sixty(self):
        csrf_token, first_token, quiz_map = self.open_quiz()
        self.assertEqual(
            self.submit_answers(csrf_token, first_token, quiz_map, correct=False).status_code,
            302,
        )
        csrf_token, second_token, quiz_map = self.open_quiz()
        self.assertEqual(
            self.submit_answers(csrf_token, second_token, quiz_map, correct=True).status_code,
            302,
        )
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            awards = conn.execute(
                "SELECT xp_awarded FROM quiz_attempts WHERE user_id = ? AND lesson_id = 1 ORDER BY id",
                (self.user_id,),
            ).fetchall()
            xp = conn.execute(
                "SELECT xp FROM user_subject_progress WHERE user_id = ? AND subject = 'math'",
                (self.user_id,),
            ).fetchone()[0]
        self.assertEqual(awards, [(10,), (50,)])
        self.assertEqual(xp, 60)

    def test_finalization_rolls_back_all_rows_on_failure(self):
        review = [{
            "question": "Rollback question",
            "user_answer": "wrong",
            "correct_answer": "right",
            "explanation": "explanation",
            "earned": 0,
            "points": 1,
        }]
        with app_module.app.test_request_context("/"):
            app_module.session["user_id"] = self.user_id
            app_module.session["subject"] = "math"
            with patch.object(app_module, "get_lessons_for_subject", side_effect=RuntimeError("forced rollback")):
                with self.assertRaises(RuntimeError):
                    app_module.finalize_quiz_attempt(
                        attempt_token="rollback-attempt-token",
                        lesson_id=1,
                        score=0,
                        total=24,
                        passed=False,
                        review=review,
                    )
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE attempt_token = 'rollback-attempt-token'").fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM mistakes WHERE user_id = ? AND question = 'Rollback question'", (self.user_id,)).fetchone()[0],
                0,
            )

    def test_locked_content_and_invalid_lessons_are_rejected(self):
        self.assertEqual(self.client.get("/lesson/2").status_code, 302)
        self.assertEqual(self.client.get("/theory/2").status_code, 403)
        self.assertEqual(self.client.get("/example/2").status_code, 403)
        token, _ = self.csrf("/lesson/1")
        self.assertEqual(
            self.client.post("/lesson/2/ready", data={"_csrf_token": token}).status_code,
            403,
        )
        self.assertEqual(self.client.get("/lesson/999").status_code, 404)
        self.assertEqual(self.client.get("/quiz/999").status_code, 404)

    def test_parallel_quiz_pages_keep_both_server_sessions(self):
        _csrf_one, token_one, _quiz_one = self.open_quiz()
        _csrf_two, token_two, _quiz_two = self.open_quiz()
        with closing(sqlite3.connect(app_module.DB_PATH)) as conn, conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM quiz_sessions WHERE attempt_token IN (?, ?)",
                (token_one, token_two),
            ).fetchone()[0]
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
