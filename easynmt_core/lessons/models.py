"""Application read models for lesson delivery and completion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from easynmt_ai.lessons import Lesson
from easynmt_core.progress import CurriculumUnitProgress


@dataclass(frozen=True)
class LessonDeliveryResult:
    lesson: Lesson
    progress: CurriculumUnitProgress
    delivery_token: str | None
    cached: bool

    @property
    def can_complete(self) -> bool:
        return self.delivery_token is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson": self.lesson.to_public_dict(),
            "progress": self.progress.to_dict(),
            "delivery_token": self.delivery_token,
            "cached": self.cached,
            "can_complete": self.can_complete,
        }


@dataclass(frozen=True)
class LessonCompletionResult:
    progress: CurriculumUnitProgress
    evidence_id: str
    completed_at: str
    idempotent: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "progress": self.progress.to_dict(),
            "evidence_id": self.evidence_id,
            "completed_at": self.completed_at,
            "idempotent": self.idempotent,
        }
