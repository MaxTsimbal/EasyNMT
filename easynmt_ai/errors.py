"""Structured failures shared by every EasyNMT AI engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Optional, TypeVar


class AIErrorCode(str, Enum):
    """Stable error codes safe to expose to application code."""

    DISABLED = "disabled"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    API_ERROR = "api_error"
    EMPTY_RESPONSE = "empty_response"
    INVALID_JSON = "invalid_json"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class AIError:
    """A provider-neutral failure returned instead of raising through Flask."""

    code: AIErrorCode
    message: str
    retryable: bool = False
    request_id: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


T = TypeVar("T")


@dataclass(frozen=True)
class EngineResult(Generic[T]):
    """Typed result envelope used by all generation and grading engines."""

    value: Optional[T] = None
    error: Optional[AIError] = None
    cached: bool = False
    usage: Optional[dict[str, Any]] = None
    response_id: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.value is not None
