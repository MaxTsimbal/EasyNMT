"""Public contracts for the Mentory learning intelligence layer."""

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
from .intelligence import build_execution_plan, build_learner_memory, polish_tutor_answer
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
from .schemas import (
    AIContext,
    AIRequest,
    AIResult,
    AIStreamEvent,
    AttachmentRef,
    LearnerMemory,
    LearningContext,
    TutorExecutionPlan,
)
from .final_solution_grading import (
    FinalSolutionGrade,
    FinalSolutionGradingEngine,
    FinalSolutionGradingItem,
)
from .written_grading import (
    CriterionGrade,
    WrittenAnswerGradingEngine,
    WrittenGradeBatch,
    WrittenGradingItem,
    WrittenQuestionGrade,
)
from .subjects import (
    ACTIVE_SUBJECT_KEYS,
    SUBJECT_REGISTRY,
    SubjectDefinition,
    active_subjects,
    get_subject,
)

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
    "ACTIVE_SUBJECT_KEYS",
    "CriterionGrade",
    "FinalSolutionGrade",
    "FinalSolutionGradingEngine",
    "FinalSolutionGradingItem",
    "WrittenAnswerGradingEngine",
    "WrittenGradeBatch",
    "WrittenGradingItem",
    "WrittenQuestionGrade",
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
    "polish_tutor_answer",
    "build_learner_memory",
    "build_execution_plan",
    "TutorExecutionPlan",
    "LearnerMemory",
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
    "SUBJECT_REGISTRY",
    "SubjectDefinition",
    "active_subjects",
    "build_cache_key",
    "validate_lesson",
    "get_subject",
]
