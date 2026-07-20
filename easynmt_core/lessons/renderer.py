"""Deterministic view preparation for structured production lessons."""
from __future__ import annotations

from easynmt_core.progress import CurriculumUnitState

from .models import LessonDeliveryResult


class CurriculumLessonRenderer:
    """Convert domain output into template data without teaching logic in Jinja."""

    def template_context(self, delivery: LessonDeliveryResult) -> dict:
        progress = delivery.progress
        return {
            "production_lesson": delivery.lesson,
            "lesson_progress": progress,
            "lesson_section_order": delivery.lesson.section_order,
            "lesson_delivery_token": delivery.delivery_token,
            "lesson_can_complete": delivery.can_complete,
            "lesson_assessment_ready": progress.state in {
                CurriculumUnitState.ASSESSMENT_REQUIRED,
                CurriculumUnitState.COMPLETED,
            },
            "lesson_cached": delivery.cached,
        }
