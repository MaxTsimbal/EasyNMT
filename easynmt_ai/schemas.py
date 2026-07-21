from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class AIContext:
    """Shared learner state passed to every AI engine.

    Values are snapshots. Engines may use them for generation but must leave
    authoritative progress, XP, and permissions to Flask and SQLite.
    """

    user_id: int
    subject: str = "none"
    goal_score: Optional[int] = None
    current_lesson: Optional[int] = None
    completed_lessons: tuple[int, ...] = field(default_factory=tuple)
    known_weaknesses: tuple[str, ...] = field(default_factory=tuple)
    recent_mistakes: tuple[str, ...] = field(default_factory=tuple)
    xp: int = 0
    language: str = "uk"
    difficulty: str = "adaptive"
    available_tokens: Optional[int] = None
    completed_topic_ids: tuple[str, ...] = field(default_factory=tuple)
    mastery_by_topic: Mapping[str, float] = field(default_factory=dict)
    diagnostic_score: Optional[int] = None
    diagnostic_total: Optional[int] = None
    study_minutes_per_week: Optional[int] = None
    desired_exam_date: Optional[str] = None
    active_curriculum_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            user_id = int(self.user_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("user_id must be a positive integer") from exc
        if user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        object.__setattr__(self, "user_id", user_id)

        subject = str(self.subject or "none").strip()[:64] or "none"
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "language", str(self.language or "uk").strip()[:16] or "uk")
        object.__setattr__(
            self,
            "difficulty",
            str(self.difficulty or "adaptive").strip()[:32] or "adaptive",
        )
        object.__setattr__(self, "xp", max(0, int(self.xp or 0)))

        goal_score = None if self.goal_score is None else int(self.goal_score)
        if goal_score is not None and goal_score < 0:
            raise ValueError("goal_score must not be negative")
        object.__setattr__(self, "goal_score", goal_score)

        current_lesson = None if self.current_lesson is None else int(self.current_lesson)
        if current_lesson is not None and current_lesson <= 0:
            raise ValueError("current_lesson must be positive")
        object.__setattr__(self, "current_lesson", current_lesson)

        completed: list[int] = []
        for value in self.completed_lessons:
            lesson_id = int(value)
            if lesson_id > 0 and lesson_id not in completed:
                completed.append(lesson_id)
        object.__setattr__(self, "completed_lessons", tuple(completed[:500]))

        def bounded_texts(values: Sequence[object], *, count: int, length: int) -> tuple[str, ...]:
            if isinstance(values, (str, bytes)):
                values = (values,)
            normalized = []
            for value in values:
                text = str(value or "").strip()
                if text:
                    normalized.append(text[:length])
                if len(normalized) >= count:
                    break
            return tuple(normalized)

        object.__setattr__(
            self,
            "known_weaknesses",
            bounded_texts(self.known_weaknesses, count=20, length=240),
        )
        object.__setattr__(
            self,
            "recent_mistakes",
            bounded_texts(self.recent_mistakes, count=20, length=700),
        )

        available_tokens = None if self.available_tokens is None else int(self.available_tokens)
        if available_tokens is not None and available_tokens <= 0:
            raise ValueError("available_tokens must be positive")
        object.__setattr__(self, "available_tokens", available_tokens)

        object.__setattr__(
            self,
            "completed_topic_ids",
            bounded_texts(self.completed_topic_ids, count=500, length=96),
        )
        if not isinstance(self.mastery_by_topic, Mapping):
            raise ValueError("mastery_by_topic must be a mapping")
        mastery = {}
        for raw_topic_id, raw_value in self.mastery_by_topic.items():
            topic_id = str(raw_topic_id or "").strip()[:96]
            if not topic_id:
                continue
            value = float(raw_value)
            if not 0 <= value <= 1:
                raise ValueError("mastery values must be between 0 and 1")
            mastery[topic_id] = round(value, 4)
        object.__setattr__(self, "mastery_by_topic", MappingProxyType(mastery))

        diagnostic_score = None if self.diagnostic_score is None else int(self.diagnostic_score)
        diagnostic_total = None if self.diagnostic_total is None else int(self.diagnostic_total)
        if diagnostic_score is not None and diagnostic_score < 0:
            raise ValueError("diagnostic_score must not be negative")
        if diagnostic_total is not None and diagnostic_total <= 0:
            raise ValueError("diagnostic_total must be positive")
        if (
            diagnostic_score is not None
            and diagnostic_total is not None
            and diagnostic_score > diagnostic_total
        ):
            raise ValueError("diagnostic_score must not exceed diagnostic_total")
        object.__setattr__(self, "diagnostic_score", diagnostic_score)
        object.__setattr__(self, "diagnostic_total", diagnostic_total)

        study_minutes = (
            None if self.study_minutes_per_week is None else int(self.study_minutes_per_week)
        )
        if study_minutes is not None and not 30 <= study_minutes <= 4200:
            raise ValueError("study_minutes_per_week must be between 30 and 4200")
        object.__setattr__(self, "study_minutes_per_week", study_minutes)

        exam_date = str(self.desired_exam_date or "").strip() or None
        if exam_date:
            try:
                date.fromisoformat(exam_date)
            except ValueError as exc:
                raise ValueError("desired_exam_date must use YYYY-MM-DD") from exc
        object.__setattr__(self, "desired_exam_date", exam_date)
        active_curriculum_id = str(self.active_curriculum_id or "").strip()[:96] or None
        object.__setattr__(self, "active_curriculum_id", active_curriculum_id)
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def for_prompt(self) -> dict[str, Any]:
        """Return the bounded, non-secret context allowed in prompts."""

        return {
            "user_id": self.user_id,
            "subject": self.subject,
            "goal_score": self.goal_score,
            "current_lesson": self.current_lesson,
            "completed_lessons": list(self.completed_lessons),
            "known_weaknesses": list(self.known_weaknesses),
            "recent_mistakes": list(self.recent_mistakes),
            "xp": max(0, int(self.xp or 0)),
            "language": self.language,
            "difficulty": self.difficulty,
            "available_tokens": self.available_tokens,
            "completed_topic_ids": list(self.completed_topic_ids),
            "mastery_by_topic": dict(self.mastery_by_topic),
            "diagnostic_score": self.diagnostic_score,
            "diagnostic_total": self.diagnostic_total,
            "study_minutes_per_week": self.study_minutes_per_week,
            "desired_exam_date": self.desired_exam_date,
            "active_curriculum_id": self.active_curriculum_id,
        }


@dataclass(frozen=True)
class LearningContext(AIContext):
    """Compatibility context for the existing tutor and lesson-chat UI."""

    user_name: str = "Учень"
    subject_key: str = "none"
    subject_name: str = "Підготовка до НМТ"
    goal: str = ""
    time_left: str = ""
    progress: int = 0
    streak: int = 1
    lesson_id: Optional[int] = None
    lesson_title: str = ""
    lesson_goal: str = ""
    weak_topic: str = ""
    weak_count: int = 0
    response_mode: str = "explain"
    lesson_context: bool = False

    def __post_init__(self) -> None:
        if self.subject == "none" and self.subject_key:
            object.__setattr__(self, "subject", self.subject_key)
        if self.current_lesson is None and self.lesson_id is not None:
            object.__setattr__(self, "current_lesson", self.lesson_id)
        if self.goal_score is None and str(self.goal).isdigit():
            object.__setattr__(self, "goal_score", int(self.goal))
        super().__post_init__()


@dataclass(frozen=True)
class LearnerMemory:
    """Small, non-sensitive learning memory used to personalize tutor replies."""

    preferred_style: str = "adaptive"
    needs_step_by_step: bool = False
    explanation_failures: int = 0
    focus_topics: tuple[str, ...] = field(default_factory=tuple)
    recent_error_patterns: tuple[str, ...] = field(default_factory=tuple)
    continuity_note: str = ""

    def __post_init__(self) -> None:
        allowed = {"adaptive", "concise", "simple", "guided", "detailed"}
        style = str(self.preferred_style or "adaptive").strip().lower()
        object.__setattr__(self, "preferred_style", style if style in allowed else "adaptive")
        object.__setattr__(self, "needs_step_by_step", bool(self.needs_step_by_step))
        object.__setattr__(self, "explanation_failures", max(0, min(99, int(self.explanation_failures or 0))))

        def bounded(values: Sequence[object], count: int, length: int) -> tuple[str, ...]:
            if isinstance(values, (str, bytes)):
                values = (values,)
            result: list[str] = []
            for value in values:
                text = str(value or "").strip()
                if text and text not in result:
                    result.append(text[:length])
                if len(result) >= count:
                    break
            return tuple(result)

        object.__setattr__(self, "focus_topics", bounded(self.focus_topics, 6, 160))
        object.__setattr__(self, "recent_error_patterns", bounded(self.recent_error_patterns, 5, 320))
        object.__setattr__(self, "continuity_note", str(self.continuity_note or "").strip()[:500])


@dataclass(frozen=True)
class TutorExecutionPlan:
    """Provider-neutral routing and response-shape plan for one tutor turn."""

    profile: str = "balanced"
    reasoning_effort: str = "low"
    verbosity: str = "medium"
    max_output_tokens: int = 900
    complexity_score: int = 1
    intent: str = "explain"

    def __post_init__(self) -> None:
        profiles = {"fast", "balanced", "deep", "vision"}
        efforts = {"none", "minimal", "low", "medium", "high", "xhigh"}
        verbosities = {"low", "medium", "high"}
        profile = str(self.profile or "balanced").strip().lower()
        effort = str(self.reasoning_effort or "low").strip().lower()
        verbosity = str(self.verbosity or "medium").strip().lower()
        object.__setattr__(self, "profile", profile if profile in profiles else "balanced")
        object.__setattr__(self, "reasoning_effort", effort if effort in efforts else "low")
        object.__setattr__(self, "verbosity", verbosity if verbosity in verbosities else "medium")
        object.__setattr__(self, "max_output_tokens", max(96, min(6000, int(self.max_output_tokens or 900))))
        object.__setattr__(self, "complexity_score", max(0, min(10, int(self.complexity_score or 0))))
        object.__setattr__(self, "intent", str(self.intent or "explain").strip()[:48] or "explain")


@dataclass(frozen=True)
class AttachmentRef:
    id: str
    original_name: str
    mime_type: str
    size_bytes: int
    stored_path: str
    kind: str = "image"


@dataclass(frozen=True)
class AIRequest:
    question: str
    context: AIContext
    history: Sequence[dict[str, str]] = field(default_factory=tuple)
    attachments: Sequence[AttachmentRef] = field(default_factory=tuple)
    fallback: str = ""
    conversation_id: str = ""
    user_message_id: str = ""
    assistant_message_id: str = ""
    learner_memory: LearnerMemory = field(default_factory=LearnerMemory)
    execution_plan: TutorExecutionPlan = field(default_factory=TutorExecutionPlan)


@dataclass
class AIResult:
    text: str
    mode: str
    error: Optional[str] = None
    response_id: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    retryable: bool = False


@dataclass
class AIStreamEvent:
    type: str
    data: dict[str, Any]
