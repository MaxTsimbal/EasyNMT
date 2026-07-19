from __future__ import annotations

from dataclasses import dataclass, field
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
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping")

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
