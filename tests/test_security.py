import os
import re
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


TEST_ROOT = tempfile.mkdtemp(prefix="easynmt-security-tests-")
os.environ["EASYNMT_DB_PATH"] = os.path.join(TEST_ROOT, "users.db")
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = TEST_ROOT
os.environ["SECRET_KEY"] = "test-only-secret-key-with-sufficient-length"
os.environ["FLASK_DEBUG"] = "0"

import app as app_module
import config as config_module
import google_oauth


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

    def test_production_rejects_weak_session_secret(self):
        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "production", "SECRET_KEY": "too-short"},
        ):
            with self.assertRaises(RuntimeError):
                config_module._secret_key()

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

    def test_login_rotates_session_state(self):
        email = "session-rotation@example.com"
        self.assertEqual(self.register(email).status_code, 302)
        token = self.csrf("/goal")
        self.assertEqual(
            self.client.post("/logout", data={"_csrf_token": token}).status_code,
            302,
        )
        token = self.csrf("/login")
        with self.client.session_transaction() as user_session:
            user_session["attacker_marker"] = "must-disappear"
        response = self.client.post(
            "/login",
            data={
                "_csrf_token": token,
                "email": email,
                "password": "correct-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertNotIn("attacker_marker", user_session)
            self.assertIn("user_id", user_session)

    def test_verified_google_email_links_existing_account(self):
        email = "google-link@example.com"
        self.assertEqual(self.register(email).status_code, 302)
        with self.client.session_transaction() as user_session:
            original_user_id = int(user_session["user_id"])
        token = self.csrf("/goal")
        self.client.post("/logout", data={"_csrf_token": token})

        profile = {
            "sub": "google-subject-link-test",
            "email": email,
            "email_verified": True,
            "name": "Google User",
            "picture": "https://example.com/avatar.png",
        }
        with patch.object(app_module, "exchange_callback", return_value=profile):
            response = self.client.get("/auth/google/callback?code=test&state=test")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertEqual(int(user_session["user_id"]), original_user_id)

        connection = app_module.get_db_connection()
        user = connection.execute(
            "SELECT google_sub FROM users WHERE id = ?",
            (original_user_id,),
        ).fetchone()
        connection.close()
        self.assertEqual(user["google_sub"], profile["sub"])

    def test_unverified_google_email_is_rejected(self):
        profile = {
            "sub": "unverified-google-subject",
            "email": "unverified-google@example.com",
            "email_verified": False,
            "name": "Unverified",
        }
        with patch.object(app_module, "exchange_callback", return_value=profile):
            response = self.client.get("/auth/google/callback?code=test&state=test")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertNotIn("user_id", user_session)

    def test_google_oauth_uses_state_and_pkce(self):
        with app_module.app.test_request_context("/"):
            with patch.dict(
                os.environ,
                {
                    "GOOGLE_CLIENT_ID": "test-client-id",
                    "GOOGLE_CLIENT_SECRET": "test-client-secret",
                },
            ):
                authorization_url = google_oauth.build_authorization_url(
                    "http://localhost/auth/google/callback"
                )
                query = parse_qs(urlparse(authorization_url).query)
                self.assertEqual(query["code_challenge_method"], ["S256"])
                self.assertEqual(query["state"], [app_module.session["google_oauth_state"]])
                self.assertNotIn(app_module.session["google_oauth_verifier"], authorization_url)
                with self.assertRaises(ValueError):
                    google_oauth.exchange_callback(
                        code="code",
                        state="wrong-state",
                        callback_url="http://localhost/auth/google/callback",
                    )

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
