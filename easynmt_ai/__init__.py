"""Public contracts for the EasyNMT learning intelligence layer."""

from .cache import AICache, NullAICache, build_cache_key
from .curriculum import CurriculumRepository, CurriculumService
from .engines import CurriculumEngine, GradingEngine, LessonEngine, QuizEngine
from .errors import AIError, AIErrorCode, EngineResult
from .lessons import (
    LESSON_SECTION_ORDER,
    LessonGenerationRequest,
    LessonValidationIssue,
    LessonValidationResult,
    validate_lesson,
)
from .models import (
    Curriculum,
    CurriculumStatus,
    CurriculumUnit,
    Feedback,
    GradeResult,
    LearningPlan,
    Lesson,
    Question,
    Quiz,
    ReviewCheckpoint,
)
from .orchestrator import AIOrchestrator
from .repository import AIRepository
from .schemas import AIContext, AIRequest, AIResult, AIStreamEvent, AttachmentRef, LearningContext

__all__ = [
    "AICache",
    "AIContext",
    "AIError",
    "AIErrorCode",
    "AIOrchestrator",
    "AIRepository",
    "AIRequest",
    "AIResult",
    "AIStreamEvent",
    "AttachmentRef",
    "Curriculum",
    "CurriculumEngine",
    "CurriculumRepository",
    "CurriculumService",
    "CurriculumStatus",
    "CurriculumUnit",
    "EngineResult",
    "Feedback",
    "GradeResult",
    "GradingEngine",
    "LearningPlan",
    "LearningContext",
    "Lesson",
    "LessonEngine",
    "LessonGenerationRequest",
    "LessonValidationIssue",
    "LessonValidationResult",
    "LESSON_SECTION_ORDER",
    "NullAICache",
    "Question",
    "Quiz",
    "QuizEngine",
    "ReviewCheckpoint",
    "build_cache_key",
    "validate_lesson",
]
