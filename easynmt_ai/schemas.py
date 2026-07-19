from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class LearningContext:
    user_id: int
    user_name: str = "Учень"
    subject_key: str = "none"
    subject_name: str = "Підготовка до НМТ"
    goal: str = ""
    time_left: str = ""
    progress: int = 0
    xp: int = 0
    streak: int = 1
    lesson_id: Optional[int] = None
    lesson_title: str = ""
    lesson_goal: str = ""
    weak_topic: str = ""
    weak_count: int = 0
    response_mode: str = "explain"
    lesson_context: bool = False


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
    context: LearningContext
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


@dataclass
class AIStreamEvent:
    type: str
    data: dict[str, Any]
