import io
import os
import re
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from tests.test_security import app_module


class AIFlowTests(unittest.TestCase):
    counter = 0

    def setUp(self):
        app_module.app.config.update(TESTING=True, AI_DAILY_UPLOAD_LIMIT=1)
        self.client = app_module.app.test_client()
        type(self).counter += 1
        self.user_id = self.onboard(f"ai-flow-{self.counter}@example.com")
        self.csrf_token = self.get_csrf("/tutor")

    def get_csrf(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        match = re.search(
            r'<meta name="csrf-token" content="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match, path)
        return match.group(1)

    def onboard(self, email):
        token = self.get_csrf("/register")
        response = self.client.post(
            "/register",
            data={
                "_csrf_token": token,
                "name": "AI Flow",
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
            token = self.get_csrf(page)
            self.assertEqual(
                self.client.post(endpoint, data={"_csrf_token": token}).status_code,
                302,
            )
        token = self.get_csrf("/diagnostic")
        answers = {
            f"q{index}": question[2]
            for index, question in enumerate(app_module.DIAGNOSTIC_BANK["math"], 1)
        }
        answers["_csrf_token"] = token
        self.assertEqual(self.client.post("/diagnostic", data=answers).status_code, 302)
        with self.client.session_transaction() as user_session:
            return int(user_session["user_id"])

    def post_json(self, path, payload):
        return self.client.post(
            path,
            json=payload,
            headers={"X-CSRF-Token": self.csrf_token},
        )

    @staticmethod
    def png_upload(name="solution.png"):
        stream = io.BytesIO()
        Image.new("RGB", (4, 4), color=(90, 120, 180)).save(stream, format="PNG")
        stream.seek(0)
        return stream, name

    def test_offline_chat_is_truthful_and_persists_server_history(self):
        status = self.client.get("/api/ai/status").get_json()
        self.assertEqual(status["mode"], "offline")
        self.assertFalse(status["vision_ready"])

        response = self.post_json(
            "/api/tutor-chat",
            {
                "question": "Як працює цей урок?",
                "conversation_id": "chat-offline",
                "user_message_id": "msg-user-offline",
                "assistant_message_id": "msg-assistant-offline",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["mode"], "offline")
        self.assertEqual(payload["used"], 0)

        with sqlite3.connect(app_module.DB_PATH) as conn:
            rows = conn.execute(
                "SELECT role, provider_mode FROM ai_messages "
                "WHERE user_id = ? AND conversation_id = ? ORDER BY rowid",
                (self.user_id, "chat-offline"),
            ).fetchall()
        self.assertEqual(rows, [("user", "user"), ("assistant", "offline")])

        feedback = self.post_json(
            "/api/ai/messages/msg-assistant-offline/feedback",
            {"rating": "up"},
        )
        self.assertEqual(feedback.status_code, 200)
        deleted = self.client.delete(
            "/api/ai/conversations/chat-offline",
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(deleted.status_code, 200)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM ai_messages WHERE user_id = ? AND conversation_id = ?",
                    (self.user_id, "chat-offline"),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM ai_message_feedback WHERE user_id = ?",
                    (self.user_id,),
                ).fetchone()[0],
                0,
            )

    def test_unknown_attachments_and_locked_lessons_are_rejected(self):
        missing = self.post_json(
            "/api/tutor-chat",
            {"question": "Перевір фото", "attachment_ids": ["att-does-not-exist"]},
        )
        self.assertEqual(missing.status_code, 400)

        locked = self.post_json(
            "/api/tutor-chat",
            {"question": "Поясни", "context": "lesson", "lesson_id": 2},
        )
        self.assertEqual(locked.status_code, 403)
        self.assertEqual(locked.get_json()["error"], "lesson_locked")

    def test_upload_limit_and_conversation_not_found_are_consistent(self):
        first = self.client.post(
            "/api/ai/attachments",
            data={"file": self.png_upload(), "conversation_id": "chat-upload"},
            headers={"X-CSRF-Token": self.csrf_token},
            content_type="multipart/form-data",
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/ai/attachments",
            data={"file": self.png_upload("second.png"), "conversation_id": "chat-upload"},
            headers={"X-CSRF-Token": self.csrf_token},
            content_type="multipart/form-data",
        )
        self.assertEqual(second.status_code, 429)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            attachment_row = conn.execute(
                "SELECT stored_path FROM ai_attachments WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()
        self.assertIsNotNone(attachment_row)

        missing = self.client.delete(
            "/api/ai/conversations/chat-upload",
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertTrue(os.path.isfile(attachment_row[0]))

        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.execute(
                "UPDATE ai_attachments SET created_at = '2000-01-01T00:00:00+00:00' "
                "WHERE user_id = ?",
                (self.user_id,),
            )
        self.assertEqual(app_module.ai_repository.prune_unattached_attachments(), 1)
        self.assertFalse(os.path.exists(attachment_row[0]))

    def test_usage_claim_is_atomic_under_concurrency(self):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.execute("DELETE FROM ai_usage WHERE user_id = ?", (self.user_id,))

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _index: app_module.claim_ai_usage(self.user_id, 3),
                    range(12),
                )
            )

        self.assertEqual(sorted(value for value in results if value is not None), [1, 2, 3])
        self.assertEqual(results.count(None), 9)
        self.assertEqual(app_module.get_ai_usage_today(self.user_id), 3)

    def test_application_pages_and_removed_demo_routes_smoke(self):
        paths = (
            "/",
            "/health",
            "/ready",
            "/about",
            "/pricing",
            "/privacy",
            "/welcome",
            "/dashboard",
            "/today",
            "/lesson/1",
            "/theory/1",
            "/example/1",
            "/quiz/1",
            "/result",
            "/progress",
            "/achievements",
            "/tutor",
            "/api/ai/status",
            "/api/ai/conversations",
            "/library",
            "/planner",
            "/mistakes",
            "/profile",
            "/settings",
            "/change-subject",
            "/robots.txt",
            "/sitemap.xml",
        )
        for path in paths:
            response = self.client.get(path)
            self.assertLess(response.status_code, 500, path)

        for path in ("/start", "/beta-check", "/v1-beta", "/api/v1-beta/curriculum"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
