"""Strict domain contracts for curriculum-unit progress."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class CurriculumUnitState(str, Enum):
    LOCKED = "locked"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    LESSON_COMPLETED = "lesson_completed"
    ASSESSMENT_REQUIRED = "assessment_required"
    COMPLETED = "completed"
    REVIEW_REQUIRED = "review_required"


class MasteryBand(str, Enum):
    UNKNOWN = "unknown"
    INTRODUCED = "introduced"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    MASTERED = "mastered"
    NEEDS_REVIEW = "needs_review"


class CheckpointState(str, Enum):
    LOCKED = "locked"
    AVAILABLE = "available"
    COMPLETED = "completed"


class LessonCompletionSource(str, Enum):
    SERVER_LESSON = "server_lesson"
    LEGACY_LESSON = "legacy_lesson"


class AssessmentSource(str, Enum):
    SERVER_QUIZ = "server_quiz"
    LEGACY_QUIZ = "legacy_quiz"
    SERVER_REVIEW = "server_review"
    CHECKPOINT_ASSESSMENT = "checkpoint_assessment"


class ReviewReason(str, Enum):
    MASTERY_DECAY = "mastery_decay"
    REPEATED_FAILURE = "repeated_failure"
    MANUAL_REVIEW = "manual_review"
    CURRICULUM_POLICY = "curriculum_policy"


def utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value


def _bounded_id(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    result = value.strip()
    if not result or len(result) > 160:
        raise ValueError(f"{field_name} is invalid")
    return result


@dataclass(frozen=True)
class LessonCompletionEvidence:
    """Server-issued evidence that lesson material was completed."""

    evidence_id: str
    verified_at: datetime
    source: LessonCompletionSource
    legacy_lesson_id: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _bounded_id(self.evidence_id, "evidence_id"))
        _aware_datetime(self.verified_at, "verified_at")
        if not isinstance(self.source, LessonCompletionSource):
            raise ValueError("source must be a LessonCompletionSource")
        if self.legacy_lesson_id is not None:
            if (
                isinstance(self.legacy_lesson_id, bool)
                or not isinstance(self.legacy_lesson_id, int)
                or self.legacy_lesson_id <= 0
            ):
                raise ValueError("legacy_lesson_id must be a positive integer")
        if (
            self.source is LessonCompletionSource.LEGACY_LESSON
            and self.legacy_lesson_id is None
        ):
            raise ValueError("legacy_lesson_id is required for legacy lesson evidence")
        if (
            self.source is LessonCompletionSource.SERVER_LESSON
            and self.legacy_lesson_id is not None
        ):
            raise ValueError("server lesson evidence cannot identify a legacy lesson")


@dataclass(frozen=True)
class ServerVerifiedAssessmentResult:
    """Assessment result created by trusted server-side grading code.

    This contract is intentionally independent from the future production Quiz
    and Grading Engines. Browser dictionaries are never accepted as evidence.
    """

    passed: bool
    score: float
    max_score: float
    attempt_id: str
    verified_at: datetime
    source: AssessmentSource

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be boolean")
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or isinstance(self.max_score, bool)
            or not isinstance(self.max_score, (int, float))
        ):
            raise ValueError("assessment scores must be numeric")
        score = float(self.score)
        maximum = float(self.max_score)
        if (
            not math.isfinite(score)
            or not math.isfinite(maximum)
            or maximum <= 0
            or score < 0
            or score > maximum
        ):
            raise ValueError("assessment score is outside the valid range")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "max_score", maximum)
        object.__setattr__(self, "attempt_id", _bounded_id(self.attempt_id, "attempt_id"))
        _aware_datetime(self.verified_at, "verified_at")
        if not isinstance(self.source, AssessmentSource):
            raise ValueError("source must be an AssessmentSource")

    @property
    def normalized_score(self) -> float:
        return round(self.score / self.max_score, 4)


@dataclass(frozen=True)
class CurriculumUnitProgress:
    id: str
    user_id: int
    curriculum_id: str
    curriculum_unit_id: str
    topic_id: str
    state: CurriculumUnitState
    mastery_score: Optional[float]
    mastery_band: MasteryBand
    attempt_count: int
    xp_awarded: int
    lesson_started_at: Optional[str]
    lesson_completed_at: Optional[str]
    assessment_required_at: Optional[str]
    completed_at: Optional[str]
    review_required_at: Optional[str]
    last_activity_at: str
    source: str
    version: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CurriculumUnitProgressView:
    unit_id: str
    topic_id: str
    title: str
    order: int
    state: CurriculumUnitState
    mastery_score: Optional[float]
    mastery_band: MasteryBand
    prerequisite_topic_ids: tuple[str, ...]
    checkpoint_status: str
    completion_timestamp: Optional[str]
    next_allowed_action: Optional[str]
    version: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CurriculumCheckpointProgressView:
    checkpoint_id: str
    after_unit_order: int
    topic_ids: tuple[str, ...]
    state: CheckpointState
    completed_at: Optional[str]
    next_allowed_action: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CurriculumProgressSnapshot:
    curriculum_id: str
    curriculum_version: int
    subject: str
    curriculum_status: str
    historical: bool
    total_units: int
    completed_units: int
    available_units: int
    in_progress_units: int
    locked_units: int
    review_required_units: int
    completion_percent: float
    current_unit_ids: tuple[str, ...]
    units: tuple[CurriculumUnitProgressView, ...] = field(default_factory=tuple)
    checkpoints: tuple[CurriculumCheckpointProgressView, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UnlockRecalculationResult:
    curriculum_id: str
    newly_available_unit_ids: tuple[str, ...] = field(default_factory=tuple)
    newly_available_checkpoint_ids: tuple[str, ...] = field(default_factory=tuple)
    unchanged: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
