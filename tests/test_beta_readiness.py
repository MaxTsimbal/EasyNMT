from contextlib import closing
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from easynmt_core.beta_readiness import (
    CORE_TABLES,
    BetaReadinessService,
    SQLiteBackupError,
    SQLiteBackupManager,
)
from tests.test_security import app_module


def create_core_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for table in sorted(CORE_TABLES):
            connection.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (id INTEGER PRIMARY KEY)')
        connection.commit()


class SQLiteBackupManagerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="easynmt-beta-backup-"))
        self.database_path = self.root / "users.db"
        self.backup_dir = self.root / "backups"
        create_core_database(self.database_path)

    def test_backup_is_verified_and_has_sha256_manifest(self):
        manager = SQLiteBackupManager(self.database_path, self.backup_dir, retention_count=3)
        result = manager.create_backup(reason="test")

        backup_path = Path(result["path"])
        manifest_path = Path(result["manifest_path"])
        self.assertTrue(backup_path.is_file())
        self.assertTrue(manifest_path.is_file())
        self.assertEqual(len(result["sha256"]), 64)
        self.assertTrue(manager.verify_backup(backup_path)["verified"])

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["sha256"], result["sha256"])
        self.assertEqual(manifest["reason"], "test")

    def test_backup_retention_removes_old_database_and_manifest(self):
        manager = SQLiteBackupManager(self.database_path, self.backup_dir, retention_count=2)
        created = []
        for index in range(3):
            result = manager.create_backup(reason=f"retention-{index}")
            created.append(Path(result["path"]))
            time.sleep(0.01)
        remaining = manager.list_backups()
        self.assertEqual(len(remaining), 2)
        self.assertFalse(created[0].exists())
        self.assertFalse(created[0].with_suffix(created[0].suffix + ".json").exists())

    def test_verify_rejects_incomplete_database(self):
        invalid = self.root / "invalid.sqlite3"
        with closing(sqlite3.connect(invalid)) as connection, connection:
            connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        manager = SQLiteBackupManager(self.database_path, self.backup_dir)
        with self.assertRaises(SQLiteBackupError):
            manager.verify_backup(invalid)


class BetaReadinessServiceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="easynmt-beta-readiness-"))
        self.database_path = self.root / "users.db"
        self.backup_dir = self.root / "backups"
        create_core_database(self.database_path)
        SQLiteBackupManager(self.database_path, self.backup_dir).create_backup(reason="seed")
        self.config = {
            "DATABASE_PATH": str(self.database_path),
            "PERSISTENT_DIR": str(self.root),
            "BACKUP_DIR": str(self.backup_dir),
            "AUTO_BACKUP_ENABLED": True,
            "BACKUP_MAX_AGE_HOURS": 30,
            "BACKUP_RETENTION_COUNT": 7,
            "BETA_MIN_FREE_BYTES": 1,
            "BETA_REQUIRE_PERSISTENT_VOLUME": True,
            "BETA_REQUIRE_OPENAI": True,
            "BETA_REQUIRE_BACKUP": True,
            "BETA_REQUIRE_GOOGLE_OAUTH": True,
            "OPENAI_API_KEY": "test-key",
            "OPENAI_WRITTEN_GRADING_ENABLED": True,
            "OPENAI_FINAL_SOLUTION_ENABLED": True,
            "OPENAI_TUTOR_MODEL": "test-model",
            "OPENAI_GRADING_MODEL": "test-model",
            "OPENAI_FINAL_SOLUTION_MODEL": "test-model",
            "SESSION_COOKIE_SECURE": True,
            "DEBUG": False,
            "WEB_CONCURRENCY": 1,
        }
        self.environment = {
            "RAILWAY_ENVIRONMENT": "production",
            "RAILWAY_VOLUME_MOUNT_PATH": str(self.root),
            "RAILWAY_GIT_COMMIT_SHA": "abc123",
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "WEB_CONCURRENCY": "1",
        }

    def test_fully_configured_beta_is_strict_ready(self):
        report = BetaReadinessService(
            self.config,
            environment=self.environment,
        ).run()
        self.assertTrue(report.ready)
        self.assertTrue(report.strict_ready)
        self.assertEqual(report.failures, 0)
        self.assertEqual(report.warnings, 0)

    def test_missing_required_openai_key_blocks_readiness(self):
        self.config["OPENAI_API_KEY"] = ""
        report = BetaReadinessService(
            self.config,
            environment=self.environment,
        ).run()
        self.assertFalse(report.ready)
        self.assertEqual(
            next(check.status for check in report.checks if check.key == "openai"),
            "fail",
        )

    def test_multiple_workers_and_partial_google_credentials_are_blocked(self):
        self.environment["WEB_CONCURRENCY"] = "2"
        self.environment["GOOGLE_CLIENT_SECRET"] = ""
        report = BetaReadinessService(
            self.config,
            environment=self.environment,
        ).run()
        statuses = {check.key: check.status for check in report.checks}
        self.assertEqual(statuses["runtime"], "fail")
        self.assertEqual(statuses["google_oauth"], "fail")
        self.assertFalse(report.ready)


class BetaRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_health_ready_and_release_headers_are_present(self):
        health = self.client.get("/health")
        ready = self.client.get("/ready")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["release"], "1.0.0-beta.1")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.get_json()["status"], "ready")
        for response in (health, ready):
            self.assertEqual(response.headers["X-EasyNMT-Version"], "1.0.0-beta.1")
            self.assertRegex(response.headers["X-Request-ID"], r"^[a-f0-9]{32}$")

    def test_valid_request_id_is_preserved_and_invalid_one_is_replaced(self):
        valid = self.client.get("/health", headers={"X-Request-ID": "beta-test-1234"})
        invalid = self.client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
        self.assertEqual(valid.headers["X-Request-ID"], "beta-test-1234")
        self.assertNotEqual(invalid.headers["X-Request-ID"], "bad id with spaces")
        self.assertRegex(invalid.headers["X-Request-ID"], r"^[a-f0-9]{32}$")

    def test_beta_cli_check_backup_and_smoke(self):
        runner = app_module.app.test_cli_runner()
        check = runner.invoke(args=["beta", "check"])
        self.assertEqual(check.exit_code, 0, check.output)
        self.assertIn("status=ready", check.output)

        backup = runner.invoke(args=["beta", "backup", "--reason", "cli-test"])
        self.assertEqual(backup.exit_code, 0, backup.output)
        self.assertIn("verified=true", backup.output)

        smoke = runner.invoke(args=["beta", "smoke"])
        self.assertEqual(smoke.exit_code, 0, smoke.output)
        self.assertIn("smoke=passed", smoke.output)

    def test_footer_uses_release_version(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("1.0.0-beta.1", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
