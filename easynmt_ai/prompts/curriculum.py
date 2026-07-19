"""Prompts for roadmap generation and future curriculum updates."""
from __future__ import annotations

import json

from ..schemas import AIContext
from .base import PromptSpec


CURRICULUM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "subject", "goal_score", "plans", "rationale"],
    "properties": {
        "id": {"type": "string"},
        "subject": {"type": "string"},
        "goal_score": {"type": ["integer", "null"]},
        "plans": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "title", "objective", "order", "difficulty",
                    "estimated_minutes", "prerequisite_ids",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "objective": {"type": "string"},
                    "order": {"type": "integer", "minimum": 1},
                    "difficulty": {"type": "string"},
                    "estimated_minutes": {"type": "integer", "minimum": 1},
                    "prerequisite_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "rationale": {"type": "string"},
    },
}


def build_curriculum_prompt(context: AIContext, *, lesson_count: int) -> PromptSpec:
    """Build a bounded request for a sequenced learning roadmap."""

    return PromptSpec(
        instructions=(
            "You are the curriculum planning engine for EasyNMT. Produce a safe, "
            "age-appropriate roadmap based only on the supplied learner snapshot. "
            "Order prerequisites before dependent topics. Do not award XP, unlock "
            "lessons, or claim to update application data. Write learner-facing "
            "content in the requested language."
        ),
        user_input=json.dumps(
            {"context": context.for_prompt(), "lesson_count": lesson_count},
            ensure_ascii=False,
            sort_keys=True,
        ),
        schema_name="easynmt_curriculum",
        schema=CURRICULUM_SCHEMA,
    )
