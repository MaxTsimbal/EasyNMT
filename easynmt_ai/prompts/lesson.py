"""Prompts for complete lesson generation."""
from __future__ import annotations

import json

from ..models import LearningPlan
from ..schemas import AIContext
from .base import PromptSpec


LESSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id", "title", "subject", "objective", "explanation", "examples",
        "practice_tasks", "summary", "difficulty", "estimated_minutes",
    ],
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "subject": {"type": "string"},
        "objective": {"type": "string"},
        "explanation": {"type": "string"},
        "examples": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "practice_tasks": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "summary": {"type": "string"},
        "difficulty": {"type": "string"},
        "estimated_minutes": {"type": "integer", "minimum": 1},
    },
}


def build_lesson_prompt(context: AIContext, plan: LearningPlan) -> PromptSpec:
    """Build a lesson request without mixing prompt text into business logic."""

    return PromptSpec(
        instructions=(
            "You are the lesson generation engine for EasyNMT. Create a complete, "
            "factually careful lesson for the supplied plan and learner snapshot. "
            "Explain concepts before practice, respect prerequisites, and do not "
            "change progress or permissions. Write in the requested language."
        ),
        user_input=json.dumps(
            {"context": context.for_prompt(), "plan": plan.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
        ),
        schema_name="easynmt_lesson",
        schema=LESSON_SCHEMA,
    )
