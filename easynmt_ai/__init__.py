"""Public contracts for the EasyNMT learning intelligence layer."""

from .cache import AICache, NullAICache, build_cache_key
from .engines import CurriculumEngine, GradingEngine, LessonEngine, QuizEngine
from .errors import AIError, AIErrorCode, EngineResult
from .models import (
    Curriculum,
    Feedback,
    GradeResult,
    LearningPlan,
    Lesson,
    Question,
    Quiz,
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
    "EngineResult",
    "Feedback",
    "GradeResult",
    "GradingEngine",
    "LearningPlan",
    "LearningContext",
    "Lesson",
    "LessonEngine",
    "NullAICache",
    "Question",
    "Quiz",
    "QuizEngine",
    "build_cache_key",
]
