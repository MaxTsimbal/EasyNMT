"""Structured contracts and validation for production lessons."""

from .models import (
    LESSON_SECTION_ORDER,
    Lesson,
    LessonAssessmentBlueprint,
    LessonAssessmentTransition,
    LessonCommonMistake,
    LessonConcept,
    LessonGenerationMetadata,
    LessonGenerationRequest,
    LessonPracticalTip,
    LessonPrerequisite,
    LessonPrerequisiteReminder,
    LessonRecap,
    WorkedExample,
    WorkedExampleStep,
)
from .validation import LessonValidationIssue, LessonValidationResult, validate_lesson

__all__ = [
    "LESSON_SECTION_ORDER",
    "Lesson",
    "LessonAssessmentBlueprint",
    "LessonAssessmentTransition",
    "LessonCommonMistake",
    "LessonConcept",
    "LessonGenerationMetadata",
    "LessonGenerationRequest",
    "LessonPracticalTip",
    "LessonPrerequisite",
    "LessonPrerequisiteReminder",
    "LessonRecap",
    "LessonValidationIssue",
    "LessonValidationResult",
    "WorkedExample",
    "WorkedExampleStep",
    "validate_lesson",
]
