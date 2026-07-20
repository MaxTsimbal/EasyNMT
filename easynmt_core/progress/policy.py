"""Deterministic state, mastery, and XP policy for curriculum progress."""
from __future__ import annotations

from typing import Optional

from .errors import InvalidProgressTransition
from .models import CurriculumUnitState, MasteryBand


CURRICULUM_UNIT_COMPLETION_XP = 60

VALID_TRANSITIONS = {
    CurriculumUnitState.LOCKED: frozenset({CurriculumUnitState.AVAILABLE}),
    CurriculumUnitState.AVAILABLE: frozenset({CurriculumUnitState.IN_PROGRESS}),
    CurriculumUnitState.IN_PROGRESS: frozenset({CurriculumUnitState.LESSON_COMPLETED}),
    CurriculumUnitState.LESSON_COMPLETED: frozenset({
        CurriculumUnitState.ASSESSMENT_REQUIRED,
    }),
    CurriculumUnitState.ASSESSMENT_REQUIRED: frozenset({CurriculumUnitState.COMPLETED}),
    CurriculumUnitState.COMPLETED: frozenset({CurriculumUnitState.REVIEW_REQUIRED}),
    CurriculumUnitState.REVIEW_REQUIRED: frozenset({
        CurriculumUnitState.IN_PROGRESS,
        CurriculumUnitState.COMPLETED,
    }),
}


def require_transition(
    previous: CurriculumUnitState,
    target: CurriculumUnitState,
) -> None:
    if target not in VALID_TRANSITIONS.get(previous, frozenset()):
        raise InvalidProgressTransition(
            f"Transition from {previous.value} to {target.value} is not allowed."
        )


def mastery_after_assessment(
    *,
    previous_score: Optional[float],
    normalized_score: float,
    passed: bool,
) -> tuple[float, MasteryBand]:
    """Apply a deliberately conservative, monotonic mastery update.

    One assessment can establish proficiency but never full mastery. Failed
    attempts can establish developing evidence without reducing prior mastery.
    """

    current = max(0.0, min(1.0, float(previous_score or 0.0)))
    if passed:
        candidate = min(0.85, max(0.65, 0.5 + normalized_score * 0.35))
        updated = max(current, candidate)
        return round(updated, 4), MasteryBand.PROFICIENT
    candidate = min(0.49, normalized_score * 0.5)
    updated = max(current, candidate)
    return round(updated, 4), MasteryBand.DEVELOPING


def next_allowed_action(state: CurriculumUnitState) -> Optional[str]:
    return {
        CurriculumUnitState.LOCKED: None,
        CurriculumUnitState.AVAILABLE: "start_lesson",
        CurriculumUnitState.IN_PROGRESS: "continue_lesson",
        CurriculumUnitState.LESSON_COMPLETED: "require_assessment",
        CurriculumUnitState.ASSESSMENT_REQUIRED: "await_server_verified_assessment",
        CurriculumUnitState.COMPLETED: None,
        CurriculumUnitState.REVIEW_REQUIRED: "start_review",
    }[state]
