"""Reusable domain models produced and consumed by EasyNMT AI engines."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional, Sequence


class AIModelValidationError(ValueError):
    """Raised when model output does not satisfy an engine's domain contract."""


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AIModelValidationError(f"{name} must be an object")
    return value


def _text(value: object, name: str, *, allow_empty: bool = False) -> str:
    result = str(value or "").strip()
    if not result and not allow_empty:
        raise AIModelValidationError(f"{name} must not be empty")
    return result


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise AIModelValidationError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AIModelValidationError(f"{name} must be an integer") from exc
    if result < minimum:
        raise AIModelValidationError(f"{name} must be at least {minimum}")
    return result


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise AIModelValidationError(f"{name} must be a boolean")
    return value


def _number(value: object, name: str, *, minimum: float = 0, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise AIModelValidationError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AIModelValidationError(f"{name} must be a number") from exc
    if result < minimum or (maximum is not None and result > maximum):
        raise AIModelValidationError(f"{name} is out of range")
    return result


def _timestamp(value: object, name: str) -> str:
    result = _text(value, name)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AIModelValidationError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise AIModelValidationError(f"{name} must include a timezone")
    return result


def _strings(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AIModelValidationError(f"{name} must be an array")
    return tuple(_text(item, f"{name} item") for item in value)


class SerializableAIModel:
    """Mixin for values that can cross the cache boundary."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Feedback(SerializableAIModel):
    message: str
    kind: str = "guidance"
    question_id: Optional[str] = None
    suggestion: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Feedback":
        data = _mapping(value, "feedback")
        return cls(
            message=_text(data.get("message"), "feedback.message"),
            kind=_text(data.get("kind", "guidance"), "feedback.kind"),
            question_id=str(data["question_id"]).strip() if data.get("question_id") else None,
            suggestion=_text(data.get("suggestion", ""), "feedback.suggestion", allow_empty=True),
        )


@dataclass(frozen=True)
class Question(SerializableAIModel):
    id: str
    prompt: str
    answer_type: str
    options: tuple[str, ...] = field(default_factory=tuple)
    correct_answer: str = ""
    explanation: str = ""
    points: int = 1

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Question":
        data = _mapping(value, "question")
        return cls(
            id=_text(data.get("id"), "question.id"),
            prompt=_text(data.get("prompt"), "question.prompt"),
            answer_type=_text(data.get("answer_type"), "question.answer_type"),
            options=_strings(data.get("options", ()), "question.options"),
            correct_answer=_text(data.get("correct_answer", ""), "question.correct_answer", allow_empty=True),
            explanation=_text(data.get("explanation", ""), "question.explanation", allow_empty=True),
            points=_integer(data.get("points", 1), "question.points", minimum=1),
        )


@dataclass(frozen=True)
class Quiz(SerializableAIModel):
    id: str
    title: str
    lesson_id: str
    questions: tuple[Question, ...]
    passing_percentage: int = 60

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Quiz":
        data = _mapping(value, "quiz")
        raw_questions = data.get("questions")
        if not isinstance(raw_questions, Sequence) or isinstance(raw_questions, (str, bytes)):
            raise AIModelValidationError("quiz.questions must be an array")
        questions = tuple(Question.from_dict(_mapping(item, "quiz question")) for item in raw_questions)
        if not questions:
            raise AIModelValidationError("quiz.questions must not be empty")
        if len({question.id for question in questions}) != len(questions):
            raise AIModelValidationError("quiz question IDs must be unique")
        passing = _integer(data.get("passing_percentage", 60), "quiz.passing_percentage")
        if passing > 100:
            raise AIModelValidationError("quiz.passing_percentage must not exceed 100")
        return cls(
            id=_text(data.get("id"), "quiz.id"),
            title=_text(data.get("title"), "quiz.title"),
            lesson_id=_text(data.get("lesson_id"), "quiz.lesson_id"),
            questions=questions,
            passing_percentage=passing,
        )


@dataclass(frozen=True)
class LearningPlan(SerializableAIModel):
    id: str
    title: str
    objective: str
    order: int
    difficulty: str
    estimated_minutes: int
    prerequisite_ids: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LearningPlan":
        data = _mapping(value, "learning plan")
        return cls(
            id=_text(data.get("id"), "learning_plan.id"),
            title=_text(data.get("title"), "learning_plan.title"),
            objective=_text(data.get("objective"), "learning_plan.objective"),
            order=_integer(data.get("order"), "learning_plan.order", minimum=1),
            difficulty=_text(data.get("difficulty"), "learning_plan.difficulty"),
            estimated_minutes=_integer(
                data.get("estimated_minutes"), "learning_plan.estimated_minutes", minimum=1
            ),
            prerequisite_ids=_strings(
                data.get("prerequisite_ids", ()), "learning_plan.prerequisite_ids"
            ),
        )


class CurriculumStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CurriculumUnit(SerializableAIModel):
    id: str
    order: int
    topic_id: str
    prerequisite_topic_ids: tuple[str, ...]
    prerequisite_explanation: str
    priority: str
    difficulty: str
    estimated_duration_minutes: int
    study_sessions: int
    mastery_target: float
    reason_code: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CurriculumUnit":
        data = _mapping(value, "curriculum unit")
        return cls(
            id=_text(data.get("id"), "curriculum_unit.id"),
            order=_integer(data.get("order"), "curriculum_unit.order", minimum=1),
            topic_id=_text(data.get("topic_id"), "curriculum_unit.topic_id"),
            prerequisite_topic_ids=_strings(
                data.get("prerequisite_topic_ids", ()),
                "curriculum_unit.prerequisite_topic_ids",
            ),
            prerequisite_explanation=_text(
                data.get("prerequisite_explanation", ""),
                "curriculum_unit.prerequisite_explanation",
                allow_empty=True,
            ),
            priority=_text(data.get("priority"), "curriculum_unit.priority"),
            difficulty=_text(data.get("difficulty"), "curriculum_unit.difficulty"),
            estimated_duration_minutes=_integer(
                data.get("estimated_duration_minutes"),
                "curriculum_unit.estimated_duration_minutes",
                minimum=1,
            ),
            study_sessions=_integer(
                data.get("study_sessions"), "curriculum_unit.study_sessions", minimum=1
            ),
            mastery_target=_number(
                data.get("mastery_target"),
                "curriculum_unit.mastery_target",
                minimum=0,
                maximum=1,
            ),
            reason_code=_text(data.get("reason_code"), "curriculum_unit.reason_code"),
        )


@dataclass(frozen=True)
class ReviewCheckpoint(SerializableAIModel):
    id: str
    after_unit_order: int
    topic_ids: tuple[str, ...]
    reason_code: str
    estimated_minutes: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReviewCheckpoint":
        data = _mapping(value, "review checkpoint")
        topic_ids = _strings(data.get("topic_ids", ()), "review_checkpoint.topic_ids")
        if not topic_ids:
            raise AIModelValidationError("review checkpoint topics must not be empty")
        return cls(
            id=_text(data.get("id"), "review_checkpoint.id"),
            after_unit_order=_integer(
                data.get("after_unit_order"),
                "review_checkpoint.after_unit_order",
                minimum=1,
            ),
            topic_ids=topic_ids,
            reason_code=_text(data.get("reason_code"), "review_checkpoint.reason_code"),
            estimated_minutes=_integer(
                data.get("estimated_minutes"),
                "review_checkpoint.estimated_minutes",
                minimum=1,
            ),
        )


@dataclass(frozen=True)
class CurriculumGenerationMetadata(SerializableAIModel):
    source: str
    context_fingerprint: str
    request_fingerprint: str
    required_topic_ids: tuple[str, ...] = field(default_factory=tuple)
    allowed_topic_ids: tuple[str, ...] = field(default_factory=tuple)
    mastered_topic_ids: tuple[str, ...] = field(default_factory=tuple)
    weakness_topic_ids: tuple[str, ...] = field(default_factory=tuple)
    review_topic_ids: tuple[str, ...] = field(default_factory=tuple)
    max_session_minutes: int = 60
    study_minutes_per_week: int = 240
    available_weeks: Optional[int] = None
    provider_response_id: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    fallback_error_code: Optional[str] = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CurriculumGenerationMetadata":
        data = _mapping(value, "curriculum generation metadata")

        def optional_integer(name: str) -> Optional[int]:
            raw = data.get(name)
            return None if raw is None else _integer(raw, f"generation_metadata.{name}")

        source = _text(data.get("source"), "generation_metadata.source")
        if source not in {"openai", "deterministic"}:
            raise AIModelValidationError("generation_metadata.source is invalid")
        return cls(
            source=source,
            context_fingerprint=_text(
                data.get("context_fingerprint"), "generation_metadata.context_fingerprint"
            ),
            request_fingerprint=_text(
                data.get("request_fingerprint"), "generation_metadata.request_fingerprint"
            ),
            required_topic_ids=_strings(
                data.get("required_topic_ids", ()),
                "generation_metadata.required_topic_ids",
            ),
            allowed_topic_ids=_strings(
                data.get("allowed_topic_ids", ()),
                "generation_metadata.allowed_topic_ids",
            ),
            mastered_topic_ids=_strings(
                data.get("mastered_topic_ids", ()),
                "generation_metadata.mastered_topic_ids",
            ),
            weakness_topic_ids=_strings(
                data.get("weakness_topic_ids", ()),
                "generation_metadata.weakness_topic_ids",
            ),
            review_topic_ids=_strings(
                data.get("review_topic_ids", ()),
                "generation_metadata.review_topic_ids",
            ),
            max_session_minutes=_integer(
                data.get("max_session_minutes", 60),
                "generation_metadata.max_session_minutes",
                minimum=1,
            ),
            study_minutes_per_week=_integer(
                data.get("study_minutes_per_week", 240),
                "generation_metadata.study_minutes_per_week",
                minimum=1,
            ),
            available_weeks=(
                None
                if data.get("available_weeks") is None
                else _integer(data.get("available_weeks"), "generation_metadata.available_weeks")
            ),
            provider_response_id=(
                str(data["provider_response_id"]).strip()
                if data.get("provider_response_id")
                else None
            ),
            input_tokens=optional_integer("input_tokens"),
            output_tokens=optional_integer("output_tokens"),
            total_tokens=optional_integer("total_tokens"),
            fallback_error_code=(
                str(data["fallback_error_code"]).strip()
                if data.get("fallback_error_code")
                else None
            ),
        )


@dataclass(frozen=True)
class Curriculum(SerializableAIModel):
    id: str
    curriculum_version: int
    taxonomy_version: str
    user_id: int
    subject: str
    target_score: int
    starting_level: str
    status: CurriculumStatus
    creation_reason: str
    units: tuple[CurriculumUnit, ...]
    review_checkpoints: tuple[ReviewCheckpoint, ...]
    generation_metadata: CurriculumGenerationMetadata
    prompt_version: str
    schema_version: str
    model_identifier: str
    created_at: str

    @property
    def goal_score(self) -> int:
        """Compatibility alias for the Task 1 curriculum contract."""

        return self.target_score

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Curriculum":
        data = _mapping(value, "curriculum")
        raw_units = data.get("units")
        if not isinstance(raw_units, Sequence) or isinstance(raw_units, (str, bytes)):
            raise AIModelValidationError("curriculum.units must be an array")
        units = tuple(CurriculumUnit.from_dict(_mapping(item, "curriculum unit")) for item in raw_units)
        if not units:
            raise AIModelValidationError("curriculum.units must not be empty")
        if len({unit.id for unit in units}) != len(units):
            raise AIModelValidationError("curriculum unit IDs must be unique")
        if len({unit.topic_id for unit in units}) != len(units):
            raise AIModelValidationError("curriculum topic IDs must be unique")
        if {unit.order for unit in units} != set(range(1, len(units) + 1)):
            raise AIModelValidationError("curriculum unit order must be contiguous")

        raw_checkpoints = data.get("review_checkpoints", ())
        if not isinstance(raw_checkpoints, Sequence) or isinstance(raw_checkpoints, (str, bytes)):
            raise AIModelValidationError("curriculum.review_checkpoints must be an array")
        checkpoints = tuple(
            ReviewCheckpoint.from_dict(_mapping(item, "review checkpoint"))
            for item in raw_checkpoints
        )
        raw_status = data.get("status")
        try:
            status = (
                raw_status
                if isinstance(raw_status, CurriculumStatus)
                else CurriculumStatus(str(raw_status))
            )
        except ValueError as exc:
            raise AIModelValidationError("curriculum.status is invalid") from exc
        target_score = _integer(data.get("target_score"), "curriculum.target_score")
        if not 100 <= target_score <= 200:
            raise AIModelValidationError("curriculum.target_score must be between 100 and 200")
        return cls(
            id=_text(data.get("id"), "curriculum.id"),
            curriculum_version=_integer(
                data.get("curriculum_version"), "curriculum.curriculum_version", minimum=1
            ),
            taxonomy_version=_text(
                data.get("taxonomy_version"), "curriculum.taxonomy_version"
            ),
            user_id=_integer(data.get("user_id"), "curriculum.user_id", minimum=1),
            subject=_text(data.get("subject"), "curriculum.subject"),
            target_score=target_score,
            starting_level=_text(data.get("starting_level"), "curriculum.starting_level"),
            status=status,
            creation_reason=_text(data.get("creation_reason"), "curriculum.creation_reason"),
            units=units,
            review_checkpoints=checkpoints,
            generation_metadata=CurriculumGenerationMetadata.from_dict(
                _mapping(data.get("generation_metadata"), "generation metadata")
            ),
            prompt_version=_text(data.get("prompt_version"), "curriculum.prompt_version"),
            schema_version=_text(data.get("schema_version"), "curriculum.schema_version"),
            model_identifier=_text(
                data.get("model_identifier"), "curriculum.model_identifier"
            ),
            created_at=_timestamp(data.get("created_at"), "curriculum.created_at"),
        )


@dataclass(frozen=True)
class Lesson(SerializableAIModel):
    id: str
    title: str
    subject: str
    objective: str
    explanation: str
    examples: tuple[str, ...]
    practice_tasks: tuple[str, ...]
    summary: str
    difficulty: str
    estimated_minutes: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Lesson":
        data = _mapping(value, "lesson")
        examples = _strings(data.get("examples", ()), "lesson.examples")
        practice_tasks = _strings(data.get("practice_tasks", ()), "lesson.practice_tasks")
        if not examples or not practice_tasks:
            raise AIModelValidationError("lesson examples and practice tasks must not be empty")
        return cls(
            id=_text(data.get("id"), "lesson.id"),
            title=_text(data.get("title"), "lesson.title"),
            subject=_text(data.get("subject"), "lesson.subject"),
            objective=_text(data.get("objective"), "lesson.objective"),
            explanation=_text(data.get("explanation"), "lesson.explanation"),
            examples=examples,
            practice_tasks=practice_tasks,
            summary=_text(data.get("summary"), "lesson.summary"),
            difficulty=_text(data.get("difficulty"), "lesson.difficulty"),
            estimated_minutes=_integer(data.get("estimated_minutes"), "lesson.estimated_minutes", minimum=1),
        )


@dataclass(frozen=True)
class GradeResult(SerializableAIModel):
    score: int
    max_score: int
    percentage: int
    passed: bool
    feedback: tuple[Feedback, ...]
    weaknesses: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GradeResult":
        data = _mapping(value, "grade result")
        score = _integer(data.get("score"), "grade_result.score")
        max_score = _integer(data.get("max_score"), "grade_result.max_score", minimum=1)
        percentage = _integer(data.get("percentage"), "grade_result.percentage")
        if score > max_score or percentage > 100:
            raise AIModelValidationError("grade result score is out of range")
        raw_feedback = data.get("feedback", ())
        if not isinstance(raw_feedback, Sequence) or isinstance(raw_feedback, (str, bytes)):
            raise AIModelValidationError("grade_result.feedback must be an array")
        return cls(
            score=score,
            max_score=max_score,
            percentage=percentage,
            passed=_boolean(data.get("passed"), "grade_result.passed"),
            feedback=tuple(Feedback.from_dict(_mapping(item, "feedback")) for item in raw_feedback),
            weaknesses=_strings(data.get("weaknesses", ()), "grade_result.weaknesses"),
        )
