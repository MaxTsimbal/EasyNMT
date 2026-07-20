"""Strict contracts for production curriculum quizzes and attempts."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping


QUESTION_TYPES = frozenset({"choice", "short_text", "long_text"})


def _text(value: object, field: str, *, maximum: int = 8000) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    result = value.strip()
    if not result or len(result) > maximum:
        raise ValueError(f"{field} is invalid")
    return result


def _string_tuple(value: object, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be a list")
    result = tuple(_text(item, field, maximum=4000) for item in value)
    if not allow_empty and not result:
        raise ValueError(f"{field} cannot be empty")
    return result


@dataclass(frozen=True)
class QuizQuestion:
    id: str
    prompt: str
    answer_type: str
    options: tuple[str, ...]
    correct_answer: str
    accepted_answers: tuple[str, ...]
    keywords: tuple[str, ...]
    explanation: str
    points: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "question.id", maximum=160))
        object.__setattr__(self, "prompt", _text(self.prompt, "question.prompt", maximum=4000))
        if self.answer_type not in QUESTION_TYPES:
            raise ValueError("question.answer_type is invalid")
        object.__setattr__(self, "options", _string_tuple(self.options, "question.options", allow_empty=True))
        object.__setattr__(self, "correct_answer", _text(self.correct_answer, "question.correct_answer", maximum=4000))
        object.__setattr__(self, "accepted_answers", _string_tuple(self.accepted_answers, "question.accepted_answers", allow_empty=True))
        object.__setattr__(self, "keywords", _string_tuple(self.keywords, "question.keywords", allow_empty=True))
        object.__setattr__(self, "explanation", _text(self.explanation, "question.explanation", maximum=8000))
        if isinstance(self.points, bool) or not isinstance(self.points, int) or self.points not in {1, 2, 3}:
            raise ValueError("question.points must be 1, 2, or 3")
        if self.answer_type == "choice":
            if len(self.options) != 4 or len(set(self.options)) != 4:
                raise ValueError("choice questions require four unique options")
            if self.correct_answer not in self.options:
                raise ValueError("choice correct answer must be one of the options")
            if self.points != 1:
                raise ValueError("choice questions must be worth one point")
        elif self.options:
            raise ValueError("written questions cannot contain options")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QuizQuestion":
        if not isinstance(value, Mapping):
            raise ValueError("question must be an object")
        return cls(
            id=value.get("id"),
            prompt=value.get("prompt"),
            answer_type=value.get("answer_type"),
            options=tuple(value.get("options") or ()),
            correct_answer=value.get("correct_answer"),
            accepted_answers=tuple(value.get("accepted_answers") or ()),
            keywords=tuple(value.get("keywords") or ()),
            explanation=value.get("explanation"),
            points=value.get("points"),
        )

    def to_dict(self, *, include_answer_key: bool = True) -> dict[str, Any]:
        result = asdict(self)
        result["options"] = list(self.options)
        result["accepted_answers"] = list(self.accepted_answers)
        result["keywords"] = list(self.keywords)
        if not include_answer_key:
            result.pop("correct_answer")
            result.pop("accepted_answers")
            result.pop("keywords")
            result.pop("explanation")
        return result


@dataclass(frozen=True)
class ProductionQuiz:
    id: str
    curriculum_id: str
    curriculum_unit_id: str
    topic_id: str
    lesson_id: str
    subject: str
    title: str
    questions: tuple[QuizQuestion, ...]
    pass_score: int = 18
    max_score: int = 24
    schema_version: str = "quiz.v1"
    generation_source: str = "deterministic"

    def __post_init__(self) -> None:
        for name in ("id", "curriculum_id", "curriculum_unit_id", "topic_id", "lesson_id", "subject", "title"):
            object.__setattr__(self, name, _text(getattr(self, name), f"quiz.{name}", maximum=240))
        if len(self.questions) != 12:
            raise ValueError("production quiz must contain exactly 12 questions")
        expected = [1] * 4 + [2] * 4 + [3] * 4
        if [item.points for item in self.questions] != expected:
            raise ValueError("production quiz must use the 4x1, 4x2, 4x3 point pattern")
        if len({item.id for item in self.questions}) != 12:
            raise ValueError("production quiz question IDs must be unique")
        if self.max_score != sum(item.points for item in self.questions) or self.max_score != 24:
            raise ValueError("production quiz maximum score must be 24")
        if self.pass_score != 18:
            raise ValueError("production quiz pass score must be 18")
        if self.generation_source not in {"deterministic", "openai"}:
            raise ValueError("quiz generation source is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProductionQuiz":
        if not isinstance(value, Mapping):
            raise ValueError("quiz must be an object")
        return cls(
            id=value.get("id"),
            curriculum_id=value.get("curriculum_id"),
            curriculum_unit_id=value.get("curriculum_unit_id"),
            topic_id=value.get("topic_id"),
            lesson_id=value.get("lesson_id"),
            subject=value.get("subject"),
            title=value.get("title"),
            questions=tuple(QuizQuestion.from_dict(item) for item in value.get("questions") or ()),
            pass_score=value.get("pass_score", 18),
            max_score=value.get("max_score", 24),
            schema_version=value.get("schema_version", "quiz.v1"),
            generation_source=value.get("generation_source", "deterministic"),
        )

    def to_dict(self, *, include_answer_key: bool = True) -> dict[str, Any]:
        return {
            "id": self.id,
            "curriculum_id": self.curriculum_id,
            "curriculum_unit_id": self.curriculum_unit_id,
            "topic_id": self.topic_id,
            "lesson_id": self.lesson_id,
            "subject": self.subject,
            "title": self.title,
            "questions": [item.to_dict(include_answer_key=include_answer_key) for item in self.questions],
            "pass_score": self.pass_score,
            "max_score": self.max_score,
            "schema_version": self.schema_version,
            "generation_source": self.generation_source,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return self.to_dict(include_answer_key=False)


@dataclass(frozen=True)
class QuizAttemptDelivery:
    attempt_token: str
    quiz: ProductionQuiz
    draft_answers: dict[str, str]
    expires_at: str
    attempt_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_token": self.attempt_token,
            "quiz": self.quiz.to_public_dict(),
            "draft_answers": dict(self.draft_answers),
            "expires_at": self.expires_at,
            "attempt_count": self.attempt_count,
        }


@dataclass(frozen=True)
class QuizAttemptResult:
    attempt_id: str
    attempt_token: str
    curriculum_unit_id: str
    score: int
    total: int
    passed: bool
    xp_awarded: int
    review: tuple[dict[str, Any], ...]
    submitted_at: str
    idempotent: bool

    def __post_init__(self) -> None:
        if not 0 <= self.score <= self.total or self.total != 24:
            raise ValueError("attempt score is invalid")
        if not isinstance(self.passed, bool):
            raise ValueError("attempt passed must be boolean")
        if self.xp_awarded < 0:
            raise ValueError("attempt xp cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "attempt_token": self.attempt_token,
            "curriculum_unit_id": self.curriculum_unit_id,
            "score": self.score,
            "total": self.total,
            "passed": self.passed,
            "xp_awarded": self.xp_awarded,
            "review": list(self.review),
            "submitted_at": self.submitted_at,
            "idempotent": self.idempotent,
        }
