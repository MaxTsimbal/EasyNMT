"""Safe, explicit bootstrap support for owner-scoped subject curricula."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from easynmt_ai.curriculum import (
    CurriculumRepository,
    CurriculumService,
    CurriculumStateError,
    validate_curriculum,
)
from easynmt_ai.schemas import AIContext


TIME_TO_WEEKLY_MINUTES = {
    "1-month": 420,
    "2-months": 300,
    "3-plus": 240,
    "6-plus": 180,
}


class CurriculumBootstrapError(RuntimeError):
    """Raised when bootstrap cannot proceed without unsafe mutation."""


@dataclass(frozen=True)
class CurriculumBootstrapUserResult:
    """One idempotent bootstrap result for one learner and one subject."""

    user_id: int
    subject: str
    curriculum_id: str
    action: str
    published: bool
    unit_ids: tuple[str, ...]
    repaired_units: int = 0
    repaired_checkpoints: int = 0
    repaired_progress_units: int = 0
    repaired_progress_checkpoints: int = 0


@dataclass(frozen=True)
class CurriculumBootstrapReport:
    database_target: str
    users: tuple[CurriculumBootstrapUserResult, ...]

    @property
    def created(self) -> int:
        return sum(item.action == "created" for item in self.users)

    @property
    def reused(self) -> int:
        return sum(item.action == "reused" for item in self.users)

    @property
    def repaired(self) -> int:
        return sum(item.action == "repaired" for item in self.users)

    @property
    def subjects(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.subject for item in self.users))


@dataclass(frozen=True)
class CurriculumDatabaseStatus:
    database_target: str
    users_count: int
    curricula_count: int
    published_curricula_count: int
    curriculum_units_count: int
    subjects: tuple[dict[str, object], ...]

    @property
    def mathematics(self) -> tuple[dict[str, object], ...]:
        """Compatibility view retained for the original mathematics CLI/tests."""

        return tuple(item for item in self.subjects if item["subject"] == "math")


class DevelopmentCurriculumBootstrapService:
    """Provision deterministic curricula without destructive reset.

    The service accepts one or more subject-specific ``CurriculumService``
    instances that share the same repository and progress service.  The old
    three-positional-argument constructor remains valid and provisions only
    the supplied service's subject by default.
    """

    def __init__(
        self,
        db_path: str,
        curriculum_service: CurriculumService | None,
        curriculum_repository: CurriculumRepository | None,
        *,
        curriculum_services: Mapping[str, CurriculumService] | None = None,
    ) -> None:
        self.db_path = str(Path(db_path).resolve())
        services = dict(curriculum_services or {})
        if curriculum_service is not None:
            services.setdefault(curriculum_service.taxonomy.subject, curriculum_service)
        if not services:
            raise ValueError("At least one curriculum service is required.")

        repository = curriculum_repository or next(iter(services.values())).repository
        if any(service.repository.db_path != repository.db_path for service in services.values()):
            raise ValueError("All curriculum services must use the same repository database.")

        self.curriculum_services = services
        self.curriculum_repository = repository
        # Compatibility aliases used by earlier Task 3B integrations.
        self.curriculum_service = services.get("math") or next(iter(services.values()))

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def production_bootstrap_allowed(*, allow_production: bool) -> bool:
        named_environment = next(
            (
                os.environ.get(name, "").strip().lower()
                for name in ("EASYNMT_ENV", "APP_ENV", "FLASK_ENV", "ENVIRONMENT")
                if os.environ.get(name, "").strip()
            ),
            "",
        )
        is_remote_or_production = bool(os.environ.get("RAILWAY_ENVIRONMENT")) or (
            named_environment == "production"
        )
        if not is_remote_or_production:
            return True
        return bool(
            allow_production
            and os.environ.get(
                "EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP",
                "",
            ).strip()
            == "1"
        )

    def status(self) -> CurriculumDatabaseStatus:
        connection = self.connect()
        try:
            users_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            curricula_count = int(
                connection.execute("SELECT COUNT(*) FROM ai_curricula").fetchone()[0]
            )
            published_count = int(connection.execute(
                "SELECT COUNT(*) FROM ai_curricula WHERE status = 'published'"
            ).fetchone()[0])
            units_count = int(
                connection.execute("SELECT COUNT(*) FROM ai_curriculum_units").fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT c.id, c.user_id, c.subject, c.status, c.curriculum_version,
                       COUNT(DISTINCT u.unit_id) AS unit_count,
                       COUNT(DISTINCT p.id) AS progress_count
                FROM ai_curricula c
                LEFT JOIN ai_curriculum_units u ON u.curriculum_id = c.id
                LEFT JOIN curriculum_unit_progress p
                  ON p.curriculum_id = c.id AND p.user_id = c.user_id
                GROUP BY c.id, c.user_id, c.subject, c.status, c.curriculum_version
                ORDER BY c.user_id, c.subject, c.curriculum_version DESC
                """
            ).fetchall()
            subject_rows = tuple({
                "curriculum_id": row["id"],
                "user_id": int(row["user_id"]),
                "subject": row["subject"],
                "status": row["status"],
                "version": int(row["curriculum_version"]),
                "unit_count": int(row["unit_count"]),
                "progress_count": int(row["progress_count"]),
            } for row in rows)
        finally:
            connection.close()
        return CurriculumDatabaseStatus(
            database_target=self.db_path,
            users_count=users_count,
            curricula_count=curricula_count,
            published_curricula_count=published_count,
            curriculum_units_count=units_count,
            subjects=subject_rows,
        )

    def _user_ids(self, requested_user_ids: Iterable[int] | None) -> tuple[int, ...]:
        requested = tuple(dict.fromkeys(int(item) for item in (requested_user_ids or ())))
        connection = self.connect()
        try:
            if requested:
                placeholders = ",".join("?" for _ in requested)
                rows = connection.execute(
                    f"SELECT id FROM users WHERE id IN ({placeholders}) ORDER BY id",
                    requested,
                ).fetchall()
                found = tuple(int(row["id"]) for row in rows)
                if set(found) != set(requested):
                    raise CurriculumBootstrapError("One or more requested users do not exist.")
                return found
            return tuple(
                int(row["id"])
                for row in connection.execute("SELECT id FROM users ORDER BY id").fetchall()
            )
        finally:
            connection.close()

    def _subject_keys(
        self,
        requested_subjects: Iterable[str] | None,
        *,
        all_subjects: bool,
    ) -> tuple[str, ...]:
        if all_subjects and requested_subjects:
            raise CurriculumBootstrapError(
                "Use either --all-subjects or one or more --subject options, not both."
            )
        if all_subjects:
            return tuple(self.curriculum_services)
        requested = tuple(dict.fromkeys(str(item).strip() for item in (requested_subjects or ())))
        if requested:
            unknown = tuple(item for item in requested if item not in self.curriculum_services)
            if unknown:
                raise CurriculumBootstrapError(
                    "Unsupported curriculum subject(s): " + ", ".join(unknown)
                )
            return requested
        # Preserve the original command behavior for callers that provide no
        # subject options: mathematics remains the default.
        if "math" in self.curriculum_services:
            return ("math",)
        return (next(iter(self.curriculum_services)),)

    def _context(self, user_id: int, subject: str) -> AIContext:
        connection = self.connect()
        try:
            plan = connection.execute(
                "SELECT goal, time_left FROM user_plans WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            diagnostic = connection.execute(
                """
                SELECT score, total, level FROM diagnostic_results
                WHERE user_id = ? AND subject = ?
                """,
                (int(user_id), subject),
            ).fetchone()
            completed_lessons = tuple(
                int(row["lesson_id"])
                for row in connection.execute(
                    """
                    SELECT lesson_id FROM completed_lessons
                    WHERE user_id = ? AND subject = ?
                    ORDER BY lesson_id
                    """,
                    (int(user_id), subject),
                ).fetchall()
            )
            xp_row = connection.execute(
                """
                SELECT xp FROM user_subject_progress
                WHERE user_id = ? AND subject = ?
                """,
                (int(user_id), subject),
            ).fetchone()
        finally:
            connection.close()

        raw_goal = str(plan["goal"] if plan and plan["goal"] else "170")
        goal_score = int(raw_goal) if raw_goal.isdigit() else 170
        if not 100 <= goal_score <= 200:
            goal_score = 170
        time_left = str(plan["time_left"] if plan and plan["time_left"] else "3-plus")
        return AIContext(
            user_id=int(user_id),
            subject=subject,
            goal_score=goal_score,
            completed_lessons=completed_lessons,
            xp=int(xp_row["xp"]) if xp_row else 0,
            language="uk",
            difficulty=(diagnostic["level"] if diagnostic else "adaptive"),
            diagnostic_score=(int(diagnostic["score"]) if diagnostic else None),
            diagnostic_total=(int(diagnostic["total"]) if diagnostic else None),
            study_minutes_per_week=TIME_TO_WEEKLY_MINUTES.get(time_left, 240),
        )

    def _ensure_user_subject(
        self,
        user_id: int,
        subject: str,
    ) -> CurriculumBootstrapUserResult:
        service = self.curriculum_services[subject]
        context = self._context(user_id, subject)
        active = service.get_active_curriculum(user_id=user_id, subject=subject)
        repaired_units = 0
        repaired_checkpoints = 0
        repaired_progress_units = 0
        repaired_progress_checkpoints = 0
        action = "reused"

        if active is None:
            draft = service.generate_baseline_curriculum_draft(context)
            if not draft.success:
                message = draft.error.message if draft.error else "unknown curriculum error"
                raise CurriculumBootstrapError(f"{subject}: {message}")
            published = service.publish_curriculum(
                user_id=user_id,
                curriculum_id=draft.value.id,
            )
            if not published.success:
                message = published.error.message if published.error else "unknown publish error"
                raise CurriculumBootstrapError(f"{subject}: {message}")
            active = published.value
            action = "reused" if draft.cached else "created"
        else:
            validation = validate_curriculum(active, service.taxonomy)
            if not validation.valid:
                expected = service.engine.deterministic_baseline(
                    context,
                    existing_curriculum=active,
                )
                try:
                    repaired = self.curriculum_repository.repair_missing_baseline_structure(
                        user_id=user_id,
                        curriculum_id=active.id,
                        expected=expected,
                    )
                except (KeyError, CurriculumStateError, sqlite3.Error) as exc:
                    raise CurriculumBootstrapError(
                        f"{subject}: existing published curriculum requires manual review; "
                        "no data was replaced."
                    ) from exc
                repaired_units = repaired["units"]
                repaired_checkpoints = repaired["checkpoints"]
                active = self.curriculum_repository.get_curriculum(user_id, active.id)
                if active is None or not validate_curriculum(
                    active,
                    service.taxonomy,
                ).valid:
                    raise CurriculumBootstrapError(
                        f"{subject}: repaired curriculum did not pass deterministic validation."
                    )
                action = "repaired" if repaired_units or repaired_checkpoints else "reused"

            progress_repaired = (
                service.progress_service
                .repair_missing_progress_for_published_curriculum(
                    user_id=user_id,
                    curriculum_id=active.id,
                )
            )
            repaired_progress_units = progress_repaired["units"]
            repaired_progress_checkpoints = progress_repaired["checkpoints"]
            if repaired_progress_units or repaired_progress_checkpoints:
                action = "repaired"

            published = service.publish_curriculum(
                user_id=user_id,
                curriculum_id=active.id,
            )
            if not published.success:
                message = published.error.message if published.error else "unknown publish error"
                raise CurriculumBootstrapError(f"{subject}: {message}")
            active = published.value

        return CurriculumBootstrapUserResult(
            user_id=user_id,
            subject=subject,
            curriculum_id=active.id,
            action=action,
            published=active.status.value == "published",
            unit_ids=tuple(unit.id for unit in active.units),
            repaired_units=repaired_units,
            repaired_checkpoints=repaired_checkpoints,
            repaired_progress_units=repaired_progress_units,
            repaired_progress_checkpoints=repaired_progress_checkpoints,
        )

    # Compatibility alias for code written before multi-subject support.
    def _ensure_user(self, user_id: int) -> CurriculumBootstrapUserResult:
        return self._ensure_user_subject(user_id, "math")

    def bootstrap(
        self,
        *,
        user_ids: Iterable[int] | None = None,
        subjects: Iterable[str] | None = None,
        all_subjects: bool = False,
        allow_production: bool = False,
    ) -> CurriculumBootstrapReport:
        if not self.production_bootstrap_allowed(allow_production=allow_production):
            raise CurriculumBootstrapError(
                "Production bootstrap requires --allow-production and "
                "EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP=1."
            )
        selected_users = self._user_ids(user_ids)
        if not selected_users:
            raise CurriculumBootstrapError(
                "No learner accounts exist. Create a normal account, then run bootstrap again."
            )
        selected_subjects = self._subject_keys(subjects, all_subjects=all_subjects)
        results = tuple(
            self._ensure_user_subject(user_id, subject)
            for user_id in selected_users
            for subject in selected_subjects
        )
        return CurriculumBootstrapReport(self.db_path, results)
