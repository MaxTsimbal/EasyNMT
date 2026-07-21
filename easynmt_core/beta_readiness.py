"""Production readiness and SQLite backup utilities for EasyNMT v1.0 Beta.

The module deliberately avoids network calls. It verifies the local runtime,
SQLite integrity, persistent storage, backup freshness, and required provider
configuration without exposing secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE_VERSION = "1.0.0-beta.1"
RELEASE_CHANNEL = "beta"

CORE_TABLES = frozenset(
    {
        "users",
        "user_plans",
        "user_subject_progress",
        "curriculum_unit_progress",
        "curriculum_lessons",
        "curriculum_quizzes",
        "ai_conversations",
    }
)


@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "status": self.status, "message": self.message}


@dataclass(frozen=True)
class BetaReadinessReport:
    checks: tuple[ReadinessCheck, ...]
    generated_at: str
    release_version: str = RELEASE_VERSION
    release_channel: str = RELEASE_CHANNEL

    @property
    def ready(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    @property
    def strict_ready(self) -> bool:
        return all(check.status == "pass" for check in self.checks)

    @property
    def warnings(self) -> int:
        return sum(check.status == "warn" for check in self.checks)

    @property
    def failures(self) -> int:
        return sum(check.status == "fail" for check in self.checks)

    def as_dict(self, *, include_checks: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "ready" if self.ready else "not_ready",
            "release": self.release_version,
            "channel": self.release_channel,
            "generated_at": self.generated_at,
            "warnings": self.warnings,
            "failures": self.failures,
        }
        if include_checks:
            payload["checks"] = [check.as_dict() for check in self.checks]
        return payload


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(timestamp: float | None = None) -> str:
    value = datetime.fromtimestamp(timestamp, timezone.utc) if timestamp is not None else _utc_now()
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SQLiteBackupError(RuntimeError):
    """Raised when a database backup cannot be created or verified."""


class SQLiteBackupManager:
    """Create, verify, and retain consistent SQLite hot backups."""

    def __init__(
        self,
        database_path: str | os.PathLike[str],
        backup_dir: str | os.PathLike[str],
        *,
        retention_count: int = 7,
        release_version: str = RELEASE_VERSION,
    ) -> None:
        self.database_path = Path(database_path)
        self.backup_dir = Path(backup_dir)
        self.retention_count = max(1, int(retention_count))
        self.release_version = release_version

    def list_backups(self) -> list[Path]:
        if not self.backup_dir.exists():
            return []
        return sorted(
            self.backup_dir.glob("easynmt-*.sqlite3"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def latest_backup(self) -> Path | None:
        backups = self.list_backups()
        return backups[0] if backups else None

    def is_recent(self, max_age_hours: float) -> bool:
        latest = self.latest_backup()
        if latest is None:
            return False
        age_seconds = max(0.0, time.time() - latest.stat().st_mtime)
        return age_seconds <= max(0.0, float(max_age_hours)) * 3600

    def verify_backup(self, backup_path: str | os.PathLike[str]) -> dict[str, Any]:
        path = Path(backup_path)
        if not path.is_file():
            raise SQLiteBackupError(f"Backup does not exist: {path}")
        try:
            with closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
            ) as connection:
                quick_check = connection.execute("PRAGMA quick_check").fetchone()
                if not quick_check or str(quick_check[0]).lower() != "ok":
                    raise SQLiteBackupError("SQLite quick_check failed")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                missing = sorted(CORE_TABLES - tables)
                if missing:
                    raise SQLiteBackupError(
                        "Backup is missing required tables: " + ", ".join(missing)
                    )
                foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
                if foreign_key_rows:
                    raise SQLiteBackupError(
                        f"Backup has {len(foreign_key_rows)} foreign-key violation(s)"
                    )
        except sqlite3.Error as exc:
            raise SQLiteBackupError(f"Cannot verify SQLite backup: {exc}") from exc
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": self._sha256(path),
            "verified": True,
        }

    def create_backup(self, *, reason: str = "manual") -> dict[str, Any]:
        if not self.database_path.is_file():
            raise SQLiteBackupError(f"Database does not exist: {self.database_path}")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        final_path = self.backup_dir / f"easynmt-{timestamp}.sqlite3"
        sequence = 1
        while final_path.exists():
            final_path = self.backup_dir / f"easynmt-{timestamp}-{sequence}.sqlite3"
            sequence += 1

        temp_handle = tempfile.NamedTemporaryFile(
            prefix=".easynmt-backup-",
            suffix=".sqlite3.tmp",
            dir=self.backup_dir,
            delete=False,
        )
        temp_path = Path(temp_handle.name)
        temp_handle.close()
        try:
            with closing(sqlite3.connect(self.database_path, timeout=30.0)) as source:
                source.execute("PRAGMA busy_timeout = 30000")
                with closing(sqlite3.connect(temp_path, timeout=30.0)) as destination:
                    source.backup(destination)
                    destination.commit()
            self.verify_backup(temp_path)
            os.replace(temp_path, final_path)
            verification = self.verify_backup(final_path)
            manifest = {
                "created_at": _iso_utc(),
                "release": self.release_version,
                "reason": str(reason)[:64],
                "database_filename": self.database_path.name,
                "backup_filename": final_path.name,
                "size_bytes": verification["size_bytes"],
                "sha256": verification["sha256"],
            }
            manifest_path = final_path.with_suffix(final_path.suffix + ".json")
            self._atomic_json_write(manifest_path, manifest)
            self.prune()
            return {**manifest, "path": str(final_path), "manifest_path": str(manifest_path)}
        except (OSError, sqlite3.Error, SQLiteBackupError) as exc:
            raise SQLiteBackupError(f"Database backup failed: {exc}") from exc
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def ensure_recent_backup(self, *, max_age_hours: float, reason: str = "automatic") -> dict[str, Any] | None:
        if self.is_recent(max_age_hours):
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.backup_dir / ".backup.lock"
        lock_fd: int | None = None
        try:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(lock_fd, f"{os.getpid()} {_iso_utc()}".encode("utf-8"))
            except FileExistsError:
                try:
                    if time.time() - lock_path.stat().st_mtime > 600:
                        lock_path.unlink(missing_ok=True)
                        return self.ensure_recent_backup(max_age_hours=max_age_hours, reason=reason)
                except OSError:
                    pass
                return None
            if self.is_recent(max_age_hours):
                return None
            return self.create_backup(reason=reason)
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def prune(self) -> None:
        for path in self.list_backups()[self.retention_count :]:
            try:
                path.unlink(missing_ok=True)
                path.with_suffix(path.suffix + ".json").unlink(missing_ok=True)
            except OSError:
                continue

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)


class BetaReadinessService:
    """Run local, deterministic checks for a controlled public beta."""

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        environment: Mapping[str, str] | None = None,
        expected_tables: Iterable[str] = CORE_TABLES,
    ) -> None:
        self.config = config
        self.environment = environment if environment is not None else os.environ
        self.expected_tables = frozenset(expected_tables)

    def run(self) -> BetaReadinessReport:
        checks = (
            self._check_database(),
            self._check_storage(),
            self._check_backups(),
            self._check_openai(),
            self._check_google_oauth(),
            self._check_runtime(),
        )
        return BetaReadinessReport(checks=checks, generated_at=_iso_utc())

    def _check_database(self) -> ReadinessCheck:
        path_value = self.config.get("DATABASE_PATH")
        if not path_value:
            return ReadinessCheck("database", "fail", "DATABASE_PATH is not configured")
        path = Path(str(path_value))
        try:
            with closing(sqlite3.connect(path, timeout=5.0)) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                quick = connection.execute("PRAGMA quick_check").fetchone()
                if not quick or str(quick[0]).lower() != "ok":
                    return ReadinessCheck("database", "fail", "SQLite quick_check failed")
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                missing = sorted(self.expected_tables - tables)
                if missing:
                    return ReadinessCheck(
                        "database",
                        "fail",
                        "Missing required tables: " + ", ".join(missing),
                    )
                violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    return ReadinessCheck(
                        "database",
                        "fail",
                        f"SQLite has {len(violations)} foreign-key violation(s)",
                    )
        except (OSError, sqlite3.Error) as exc:
            return ReadinessCheck("database", "fail", f"SQLite unavailable: {exc}")
        return ReadinessCheck("database", "pass", "SQLite is reachable and consistent")

    def _check_storage(self) -> ReadinessCheck:
        database_path = Path(str(self.config.get("DATABASE_PATH", "")))
        persistent_dir = Path(
            str(self.config.get("PERSISTENT_DIR") or database_path.parent or ".")
        )
        railway = bool(self.environment.get("RAILWAY_ENVIRONMENT"))
        mounted_volume = bool(self.environment.get("RAILWAY_VOLUME_MOUNT_PATH"))
        require_volume = _as_bool(
            self.config.get("BETA_REQUIRE_PERSISTENT_VOLUME"),
            default=railway,
        )
        if railway and require_volume and not mounted_volume:
            return ReadinessCheck(
                "storage",
                "fail",
                "Railway persistent volume is required but not mounted",
            )
        try:
            persistent_dir.mkdir(parents=True, exist_ok=True)
            probe = tempfile.NamedTemporaryFile(
                prefix=".easynmt-write-probe-",
                dir=persistent_dir,
                delete=False,
            )
            probe_path = Path(probe.name)
            probe.write(b"ok")
            probe.flush()
            os.fsync(probe.fileno())
            probe.close()
            probe_path.unlink(missing_ok=True)
            free_bytes = shutil.disk_usage(persistent_dir).free
        except OSError as exc:
            return ReadinessCheck("storage", "fail", f"Persistent storage is not writable: {exc}")
        minimum = _safe_int(self.config.get("BETA_MIN_FREE_BYTES"), 20 * 1024 * 1024)
        if free_bytes < minimum:
            return ReadinessCheck(
                "storage",
                "fail",
                f"Persistent storage has only {free_bytes} free bytes",
            )
        if railway and not mounted_volume:
            return ReadinessCheck(
                "storage",
                "warn",
                "Railway volume is not mounted; data can disappear on redeploy",
            )
        return ReadinessCheck("storage", "pass", "Persistent storage is writable")

    def _check_backups(self) -> ReadinessCheck:
        enabled = _as_bool(self.config.get("AUTO_BACKUP_ENABLED"), default=True)
        required = _as_bool(self.config.get("BETA_REQUIRE_BACKUP"), default=False)
        if not enabled:
            return ReadinessCheck(
                "backups",
                "fail" if required else "warn",
                "Automatic database backups are disabled",
            )
        database_path = self.config.get("DATABASE_PATH")
        backup_dir = self.config.get("BACKUP_DIR")
        if not database_path or not backup_dir:
            return ReadinessCheck("backups", "fail", "Backup paths are not configured")
        manager = SQLiteBackupManager(
            str(database_path),
            str(backup_dir),
            retention_count=_safe_int(self.config.get("BACKUP_RETENTION_COUNT"), 7),
        )
        latest = manager.latest_backup()
        if latest is None:
            return ReadinessCheck(
                "backups",
                "fail" if required else "warn",
                "No verified database backup exists yet",
            )
        max_age = float(self.config.get("BACKUP_MAX_AGE_HOURS", 30))
        if not manager.is_recent(max_age):
            return ReadinessCheck(
                "backups",
                "fail" if required else "warn",
                "Latest database backup is stale",
            )
        try:
            manager.verify_backup(latest)
        except SQLiteBackupError as exc:
            return ReadinessCheck("backups", "fail", str(exc))
        return ReadinessCheck("backups", "pass", "A recent verified SQLite backup exists")

    def _check_openai(self) -> ReadinessCheck:
        key_present = bool(str(self.config.get("OPENAI_API_KEY", "")).strip())
        written_enabled = _as_bool(self.config.get("OPENAI_WRITTEN_GRADING_ENABLED"), True)
        vision_enabled = _as_bool(self.config.get("OPENAI_FINAL_SOLUTION_ENABLED"), True)
        require_openai = _as_bool(self.config.get("BETA_REQUIRE_OPENAI"), True)
        active = written_enabled or vision_enabled
        if active and not key_present:
            status = "fail" if require_openai else "warn"
            return ReadinessCheck(
                "openai",
                status,
                "OpenAI is required for AI grading but OPENAI_API_KEY is missing",
            )
        model_keys = (
            "OPENAI_TUTOR_MODEL",
            "OPENAI_GRADING_MODEL",
            "OPENAI_FINAL_SOLUTION_MODEL",
        )
        missing_models = [key for key in model_keys if not str(self.config.get(key, "")).strip()]
        if key_present and missing_models:
            return ReadinessCheck(
                "openai",
                "fail",
                "Missing model configuration: " + ", ".join(missing_models),
            )
        if not key_present:
            return ReadinessCheck("openai", "warn", "OpenAI is offline")
        return ReadinessCheck("openai", "pass", "OpenAI credentials and model routing are configured")

    def _check_google_oauth(self) -> ReadinessCheck:
        client_id = str(self.environment.get("GOOGLE_CLIENT_ID", "")).strip()
        client_secret = str(self.environment.get("GOOGLE_CLIENT_SECRET", "")).strip()
        require_google = _as_bool(self.config.get("BETA_REQUIRE_GOOGLE_OAUTH"), False)
        if bool(client_id) != bool(client_secret):
            return ReadinessCheck(
                "google_oauth",
                "fail",
                "Google OAuth credentials are only partially configured",
            )
        if not client_id:
            return ReadinessCheck(
                "google_oauth",
                "fail" if require_google else "warn",
                "Google OAuth is not configured; email login remains available",
            )
        return ReadinessCheck("google_oauth", "pass", "Google OAuth credentials are configured")

    def _check_runtime(self) -> ReadinessCheck:
        railway = bool(self.environment.get("RAILWAY_ENVIRONMENT"))
        debug = _as_bool(self.config.get("DEBUG"), False)
        secure_cookie = _as_bool(self.config.get("SESSION_COOKIE_SECURE"), False)
        workers = _safe_int(
            self.environment.get("WEB_CONCURRENCY") or self.config.get("WEB_CONCURRENCY"),
            1,
        )
        if workers > 1:
            return ReadinessCheck(
                "runtime",
                "fail",
                "SQLite beta deployment supports exactly one web worker",
            )
        if railway and debug:
            return ReadinessCheck("runtime", "fail", "Debug mode is enabled in production")
        if railway and not secure_cookie:
            return ReadinessCheck("runtime", "fail", "Secure session cookies are disabled")
        commit = str(self.environment.get("RAILWAY_GIT_COMMIT_SHA", "")).strip()
        if railway and not commit:
            return ReadinessCheck(
                "runtime",
                "warn",
                "Railway commit metadata is unavailable",
            )
        return ReadinessCheck("runtime", "pass", "Single-worker production runtime is configured")
