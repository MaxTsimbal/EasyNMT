import os
import re
import tempfile
import unittest


TEST_ROOT = tempfile.mkdtemp(prefix="easynmt-security-tests-")
os.environ["EASYNMT_DB_PATH"] = os.path.join(TEST_ROOT, "users.db")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = TEST_ROOT
os.environ["SECRET_KEY"] = "test-only-secret-key-with-sufficient-length"
os.environ["FLASK_DEBUG"] = "0"

import app as app_module


class SecurityFlowTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def csrf(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        match = re.search(
            r'<meta name="csrf-token" content="([^"]+)"',
            response.get_data(as_text=True),
        )
        self.assertIsNotNone(match, path)
        return match.group(1)

    def register(self, email):
        token = self.csrf("/register")
        return self.client.post(
            "/register",
            data={
                "_csrf_token": token,
                "name": "Security Test",
                "email": email,
                "password": "correct-password",
                "confirm_password": "correct-password",
            },
        )

    def test_unsafe_request_requires_csrf(self):
        self.csrf("/register")
        response = self.client.post(
            "/register",
            data={
                "name": "Missing Token",
                "email": "missing-token@example.com",
                "password": "correct-password",
                "confirm_password": "correct-password",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_onboarding_mutations_are_post_only_and_validated(self):
        response = self.register("onboarding-security@example.com")
        self.assertEqual(response.status_code, 302)

        for path in ("/set-goal/170", "/set-subject/math", "/set-time/3-plus", "/logout"):
            self.assertEqual(self.client.get(path).status_code, 405, path)
        self.assertEqual(self.client.get("/start").status_code, 404)

        token = self.csrf("/goal")
        self.assertEqual(
            self.client.post("/set-goal/not-a-goal", data={"_csrf_token": token}).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/set-goal/170", data={"_csrf_token": token}).status_code,
            302,
        )
        token = self.csrf("/subject")
        self.assertEqual(
            self.client.post("/set-subject/math", data={"_csrf_token": token}).status_code,
            302,
        )
        token = self.csrf("/date")
        self.assertEqual(
            self.client.post("/set-time/3-plus", data={"_csrf_token": token}).status_code,
            302,
        )

    def test_registration_validates_email_and_password(self):
        token = self.csrf("/register")
        response = self.client.post(
            "/register",
            data={
                "_csrf_token": token,
                "name": "Invalid",
                "email": "not-an-email",
                "password": "short",
                "confirm_password": "short",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("коректну email", response.get_data(as_text=True))

    def test_login_failures_are_throttled(self):
        token = self.csrf("/login")
        for _ in range(app_module.LOGIN_FAILURE_LIMIT):
            response = self.client.post(
                "/login",
                data={
                    "_csrf_token": token,
                    "email": "throttled@example.com",
                    "password": "wrong-password",
                },
            )
            self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/login",
            data={
                "_csrf_token": token,
                "email": "throttled@example.com",
                "password": "wrong-password",
            },
        )
        self.assertEqual(response.status_code, 429)

    def test_security_headers_are_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "strict-origin-when-cross-origin")

    def test_liveness_and_database_readiness_are_distinct(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 200)
        original_path = app_module.app.config["DATABASE_PATH"]
        try:
            app_module.app.config["DATABASE_PATH"] = ":memory:"
            response = self.client.get("/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json()["status"], "not_ready")
        finally:
            app_module.app.config["DATABASE_PATH"] = original_path


if __name__ == "__main__":
    unittest.main()
