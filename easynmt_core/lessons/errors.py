"""Typed production lesson failures safe for API translation."""
from __future__ import annotations


class CurriculumLessonError(Exception):
    code = "curriculum_lesson_error"
    http_status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CurriculumLessonNotFound(CurriculumLessonError):
    code = "curriculum_lesson_not_found"
    http_status = 404


class CurriculumLessonOwnershipError(CurriculumLessonError):
    code = "curriculum_lesson_ownership_error"
    http_status = 403


class CurriculumLessonNotAvailable(CurriculumLessonError):
    code = "curriculum_lesson_not_available"
    http_status = 409


class CurriculumLessonGenerationUnavailable(CurriculumLessonError):
    code = "curriculum_lesson_generation_unavailable"
    http_status = 503


class CurriculumLessonDeliveryInvalid(CurriculumLessonError):
    code = "curriculum_lesson_delivery_invalid"
    http_status = 400


class CurriculumLessonConflict(CurriculumLessonError):
    code = "curriculum_lesson_conflict"
    http_status = 409


class CurriculumLessonPersistenceError(CurriculumLessonError):
    code = "curriculum_lesson_persistence_error"
    http_status = 500
