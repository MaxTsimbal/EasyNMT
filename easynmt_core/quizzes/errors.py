"""Errors raised by the production curriculum quiz subsystem."""


class CurriculumQuizError(RuntimeError):
    """Base class for quiz delivery, grading, and persistence failures."""


class CurriculumQuizNotAvailable(CurriculumQuizError):
    """The curriculum unit is not currently eligible for a quiz."""


class CurriculumQuizNotFound(CurriculumQuizError):
    """The requested quiz, attempt, or curriculum unit does not exist."""


class CurriculumQuizOwnershipError(CurriculumQuizError):
    """The requested quiz resource belongs to another learner."""


class CurriculumQuizSessionInvalid(CurriculumQuizError):
    """The server-issued attempt token is invalid, expired, or mismatched."""


class CurriculumQuizPersistenceError(CurriculumQuizError):
    """Stored quiz content failed integrity or schema validation."""


class CurriculumQuizConflict(CurriculumQuizError):
    """Concurrent or conflicting quiz finalization was detected."""


class CurriculumQuizAnswersIncomplete(CurriculumQuizError):
    """A final submission omitted one or more required quiz answers."""

    def __init__(self, missing_questions):
        normalized = tuple(sorted({int(number) for number in missing_questions if int(number) > 0}))
        self.missing_questions = normalized
        super().__init__(
            "Complete every quiz question before final submission. Missing: "
            + ", ".join(str(number) for number in normalized)
        )


class CurriculumQuizPhotoError(CurriculumQuizError):
    """Base class for question 12 photo validation or grading failures."""


class CurriculumQuizPhotoUnreadable(CurriculumQuizPhotoError):
    """The uploaded solution image is too unclear to grade safely."""


class CurriculumQuizPhotoUnavailable(CurriculumQuizPhotoError):
    """A photo-only submission could not be graded by the vision service."""
