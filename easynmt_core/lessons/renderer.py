"""Deterministic view preparation for structured production lessons."""
from __future__ import annotations

from easynmt_core.progress import CurriculumProgressSnapshot, CurriculumUnitState

from .models import LessonDeliveryResult


class CurriculumLessonRenderer:
    """Convert domain output into template data without teaching logic in Jinja."""

    @staticmethod
    def navigation_context(snapshot: CurriculumProgressSnapshot) -> dict:
        """Build one presentation-ready navigation model from authoritative progress."""

        open_states = {
            CurriculumUnitState.IN_PROGRESS,
            CurriculumUnitState.LESSON_COMPLETED,
            CurriculumUnitState.ASSESSMENT_REQUIRED,
            CurriculumUnitState.COMPLETED,
        }
        start_states = {
            CurriculumUnitState.AVAILABLE,
            CurriculumUnitState.REVIEW_REQUIRED,
        }
        status_labels = {
            CurriculumUnitState.LOCKED: "Ще закрито",
            CurriculumUnitState.AVAILABLE: "Відкрито",
            CurriculumUnitState.IN_PROGRESS: "Зараз",
            CurriculumUnitState.LESSON_COMPLETED: "Урок пройдено",
            CurriculumUnitState.ASSESSMENT_REQUIRED: "Очікує перевірки",
            CurriculumUnitState.COMPLETED: "Пройдено",
            CurriculumUnitState.REVIEW_REQUIRED: "Потрібне повторення",
        }
        action_labels = {
            CurriculumUnitState.AVAILABLE: "Почати тему →",
            CurriculumUnitState.IN_PROGRESS: "Продовжити →",
            CurriculumUnitState.LESSON_COMPLETED: "Переглянути урок →",
            CurriculumUnitState.ASSESSMENT_REQUIRED: "Повторити урок →",
            CurriculumUnitState.COMPLETED: "Повторити",
            CurriculumUnitState.REVIEW_REQUIRED: "Почати повторення →",
        }
        descriptions = {
            CurriculumUnitState.LOCKED: "Спочатку виконай передумови маршруту.",
            CurriculumUnitState.AVAILABLE: "Тема готова до початку.",
            CurriculumUnitState.IN_PROGRESS: "Продовжуй структурований AI-урок.",
            CurriculumUnitState.LESSON_COMPLETED: "Матеріал завершено; далі перевірка.",
            CurriculumUnitState.ASSESSMENT_REQUIRED: "Можеш повторити матеріал перед перевіркою.",
            CurriculumUnitState.COMPLETED: "Тему й перевірку завершено.",
            CurriculumUnitState.REVIEW_REQUIRED: "Повтори матеріал перед новою перевіркою.",
        }
        priority = {
            CurriculumUnitState.IN_PROGRESS: 0,
            CurriculumUnitState.LESSON_COMPLETED: 1,
            CurriculumUnitState.ASSESSMENT_REQUIRED: 2,
            CurriculumUnitState.REVIEW_REQUIRED: 3,
            CurriculumUnitState.AVAILABLE: 4,
            CurriculumUnitState.COMPLETED: 5,
            CurriculumUnitState.LOCKED: 6,
        }
        if snapshot.completed_units == snapshot.total_units and snapshot.units:
            selected = max(snapshot.units, key=lambda item: item.order)
        else:
            selected = min(snapshot.units, key=lambda item: (priority[item.state], item.order))
        units = tuple({
            "unit_id": item.unit_id,
            "topic_id": item.topic_id,
            "title": item.title,
            "order": item.order,
            "state": item.state.value,
            "status_label": status_labels[item.state],
            "action_label": action_labels.get(item.state, "Ще закрито"),
            "description": descriptions[item.state],
            "can_open": item.state in open_states,
            "can_start": item.state in start_states,
            "is_locked": item.state is CurriculumUnitState.LOCKED,
            "is_completed": item.state is CurriculumUnitState.COMPLETED,
            "is_current": item.unit_id == selected.unit_id,
            "mastery_score": item.mastery_score,
            "mastery_band": item.mastery_band.value,
        } for item in snapshot.units)
        current_index = next(index for index, item in enumerate(units) if item["is_current"])
        current = units[current_index]

        # The dashboard should show a small, useful window instead of the full
        # curriculum wall. Keep the current topic in the middle whenever
        # possible, with one nearby topic on each side. The complete route
        # remains available in the library.
        preview_limit = 3
        if len(units) <= preview_limit:
            preview_start = 0
        elif snapshot.completed_units == snapshot.total_units:
            preview_start = len(units) - preview_limit
        else:
            preview_start = max(0, min(current_index - 1, len(units) - preview_limit))
        nearby_units = units[preview_start:preview_start + preview_limit]

        return {
            "curriculum_id": snapshot.curriculum_id,
            "subject": snapshot.subject,
            "units": units,
            "nearby_units": nearby_units,
            "other_units_count": max(0, len(units) - len(nearby_units)),
            "current_unit": current,
            "completed_count": snapshot.completed_units,
            "total_count": snapshot.total_units,
            "progress_percent": round(snapshot.completion_percent),
            "journey_complete": snapshot.completed_units == snapshot.total_units,
        }

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
