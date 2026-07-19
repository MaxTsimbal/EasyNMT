"""Reusable domain models produced and consumed by EasyNMT AI engines."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
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


@dataclass(frozen=True)
class Curriculum(SerializableAIModel):
    id: str
    subject: str
    goal_score: Optional[int]
    plans: tuple[LearningPlan, ...]
    rationale: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Curriculum":
        data = _mapping(value, "curriculum")
        raw_plans = data.get("plans")
        if not isinstance(raw_plans, Sequence) or isinstance(raw_plans, (str, bytes)):
            raise AIModelValidationError("curriculum.plans must be an array")
        plans = tuple(LearningPlan.from_dict(_mapping(item, "curriculum plan")) for item in raw_plans)
        if not plans:
            raise AIModelValidationError("curriculum.plans must not be empty")
        plan_ids = {plan.id for plan in plans}
        if len(plan_ids) != len(plans):
            raise AIModelValidationError("curriculum plan IDs must be unique")
        if {plan.order for plan in plans} != set(range(1, len(plans) + 1)):
            raise AIModelValidationError("curriculum plan order must be contiguous")
        plan_order = {plan.id: plan.order for plan in plans}
        for plan in plans:
            for prerequisite_id in plan.prerequisite_ids:
                if prerequisite_id not in plan_order:
                    raise AIModelValidationError("curriculum prerequisite is unknown")
                if plan_order[prerequisite_id] >= plan.order:
                    raise AIModelValidationError("curriculum prerequisite must appear earlier")
        raw_goal = data.get("goal_score")
        goal_score = None if raw_goal is None else _integer(raw_goal, "curriculum.goal_score")
        return cls(
            id=_text(data.get("id"), "curriculum.id"),
            subject=_text(data.get("subject"), "curriculum.subject"),
            goal_score=goal_score,
            plans=plans,
            rationale=_text(data.get("rationale", ""), "curriculum.rationale", allow_empty=True),
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
