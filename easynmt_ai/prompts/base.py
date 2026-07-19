"""Prompt transport values shared by all AI engines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PromptSpec:
    """A complete provider-neutral prompt and its expected JSON schema."""

    instructions: str
    user_input: str
    schema_name: str
    schema: Mapping[str, Any]
