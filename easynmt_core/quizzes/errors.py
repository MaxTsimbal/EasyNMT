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
