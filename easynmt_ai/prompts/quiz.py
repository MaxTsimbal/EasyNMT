"""Prompts for lesson-bound quiz generation."""
from __future__ import annotations

import json

from ..models import Lesson
from ..schemas import AIContext
from .base import PromptSpec


QUESTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id", "prompt", "answer_type", "options", "correct_answer",
        "explanation", "points",
    ],
    "properties": {
        "id": {"type": "string"},
        "prompt": {"type": "string"},
        "answer_type": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "correct_answer": {"type": "string"},
        "explanation": {"type": "string"},
        "points": {"type": "integer", "minimum": 1},
    },
}

QUIZ_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "title", "lesson_id", "questions", "passing_percentage"],
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "lesson_id": {"type": "string"},
        "questions": {"type": "array", "minItems": 1, "items": QUESTION_SCHEMA},
        "passing_percentage": {"type": "integer", "minimum": 0, "maximum": 100},
    },
}


def build_quiz_prompt(context: AIContext, lesson: Lesson, *, question_count: int) -> PromptSpec:
    """Build a quiz request whose content is constrained to one lesson."""

    return PromptSpec(
        instructions=(
            "You are the quiz generation engine for EasyNMT. Test only concepts "
            "present in the supplied lesson. Provide unambiguous questions, exact "
            "answer keys, and short explanations. Do not grade or persist anything. "
            "Write learner-facing text in the requested language."
        ),
        user_input=json.dumps(
            {
                "context": context.for_prompt(),
                "lesson": lesson.to_dict(),
                "question_count": question_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        schema_name="easynmt_quiz",
        schema=QUIZ_SCHEMA,
    )
