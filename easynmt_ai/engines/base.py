"""Base contract implemented by all EasyNMT AI engines."""
from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from ..orchestrator import AIOrchestrator


T = TypeVar("T")


class AIEngine(ABC, Generic[T]):
    """Shared engine dependency contract.

    Engines receive an orchestrator rather than an OpenAI client. This keeps
    provider access, telemetry, retries, and response handling centralized.
    """

    name = "base"
    cache_namespace = "base"
    cache_ttl_seconds: int | None = None

    def __init__(self, orchestrator: "AIOrchestrator") -> None:
        self.orchestrator = orchestrator
