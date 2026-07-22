"""Production prompt and strict schema for complete educational lessons."""
from __future__ import annotations

import json
from typing import Any

from ..lessons.models import LessonGenerationRequest
from ..schemas import AIContext
from ..subjects import get_subject
from .base import PromptSpec


LESSON_PROMPT_VERSION = "lesson-production-1.1"
LESSON_SCHEMA_VERSION = "lesson-structured-1.1"


def _string(minimum: int = 1) -> dict[str, Any]:
    return {"type": "string", "minLength": minimum}


def _string_array(minimum: int = 1) -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": minimum,
        "items": _string(1),
    }


CONCEPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "title",
        "what",
        "why",
        "how",
        "when_used",
        "nmt_use",
        "common_confusion",
        "competency_indices",
    ],
    "properties": {
        "id": _string(),
        "title": _string(),
        "what": _string(35),
        "why": _string(25),
        "how": _string(45),
        "when_used": _string(25),
        "nmt_use": _string(25),
        "common_confusion": _string(25),
        "competency_indices": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 1},
        },
    },
}

EXAMPLE_STEP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["order", "work", "explanation"],
    "properties": {
        "order": {"type": "integer", "minimum": 1},
        "work": _string(),
        "explanation": _string(20),
    },
}

WORKED_EXAMPLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "difficulty",
        "problem",
        "reasoning",
        "concept_ids",
        "steps",
        "final_answer",
        "verification",
    ],
    "properties": {
        "id": _string(),
        "difficulty": {"type": "string", "enum": ["foundation", "guided", "exam"]},
        "problem": _string(),
        "reasoning": _string(35),
        "concept_ids": _string_array(),
        "steps": {
            "type": "array",
            "minItems": 2,
            "items": EXAMPLE_STEP_SCHEMA,
        },
        "final_answer": _string(),
        "verification": _string(20),
    },
}

COMMON_MISTAKE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "incorrect_reasoning",
        "why_incorrect",
        "recognition",
        "correction",
        "prevention",
        "concept_ids",
    ],
    "properties": {
        "id": _string(),
        "incorrect_reasoning": _string(20),
        "why_incorrect": _string(20),
        "recognition": _string(20),
        "correction": _string(20),
        "prevention": _string(20),
        "concept_ids": _string_array(),
    },
}

PRACTICAL_TIP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "advice", "use_when", "recognition_pattern"],
    "properties": {
        "id": _string(),
        "advice": _string(),
        "use_when": _string(),
        "recognition_pattern": _string(),
    },
}

GUIDED_PRACTICE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "difficulty",
        "prompt",
        "hint",
        "solution_steps",
        "expected_answer",
        "explanation",
        "concept_ids",
    ],
    "properties": {
        "id": _string(),
        "difficulty": {"type": "string", "enum": ["foundation", "guided", "exam"]},
        "prompt": _string(20),
        "hint": _string(15),
        "solution_steps": {
            "type": "array",
            "minItems": 2,
            "items": _string(10),
        },
        "expected_answer": _string(),
        "explanation": _string(25),
        "concept_ids": _string_array(),
    },
}

LESSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "objective_overview",
        "nmt_relevance",
        "nmt_task_types",
        "prerequisite_reminder",
        "concepts",
        "worked_examples",
        "common_mistakes",
        "practical_tips",
        "guided_practice",
        "recap",
        "assessment_transition",
        "assessment_blueprint",
    ],
    "properties": {
        "objective_overview": _string(40),
        "nmt_relevance": _string(60),
        "nmt_task_types": _string_array(2),
        "prerequisite_reminder": {
            "type": "object",
            "additionalProperties": False,
            "required": ["needed", "explanation", "points"],
            "properties": {
                "needed": {"type": "boolean"},
                "explanation": {"type": "string"},
                "points": {"type": "array", "items": _string()},
            },
        },
        "concepts": {
            "type": "array",
            "minItems": 2,
            "items": CONCEPT_SCHEMA,
        },
        "worked_examples": {
            "type": "array",
            "minItems": 3,
            "items": WORKED_EXAMPLE_SCHEMA,
        },
        "common_mistakes": {
            "type": "array",
            "minItems": 3,
            "items": COMMON_MISTAKE_SCHEMA,
        },
        "practical_tips": {
            "type": "array",
            "minItems": 3,
            "items": PRACTICAL_TIP_SCHEMA,
        },
        "guided_practice": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": GUIDED_PRACTICE_SCHEMA,
        },
        "recap": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "main_ideas",
                "formulas",
                "warnings",
                "recognition_patterns",
                "can_solve",
            ],
            "properties": {
                "main_ideas": _string_array(2),
                "formulas": _string_array(1),
                "warnings": _string_array(2),
                "recognition_patterns": _string_array(2),
                "can_solve": _string_array(2),
            },
        },
        "assessment_transition": {
            "type": "object",
            "additionalProperties": False,
            "required": ["message", "readiness_checklist"],
            "properties": {
                "message": _string(40),
                "readiness_checklist": _string_array(4),
            },
        },
        "assessment_blueprint": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "covered_concept_ids",
                "question_patterns",
                "required_reasoning",
                "excluded_content",
            ],
            "properties": {
                "covered_concept_ids": _string_array(2),
                "question_patterns": _string_array(4),
                "required_reasoning": _string_array(2),
                "excluded_content": {"type": "array", "items": _string()},
            },
        },
    },
}


def lesson_prompt_context(
    context: AIContext,
    request: LessonGenerationRequest,
) -> dict[str, Any]:
    """Bound personalization without IDs, XP, or raw learner mistakes."""

    mastery = context.mastery_by_topic.get(request.topic_id)
    diagnostic_ratio = None
    if context.diagnostic_score is not None and context.diagnostic_total:
        diagnostic_ratio = round(context.diagnostic_score / context.diagnostic_total, 3)
    return {
        "language": request.language,
        "target_score": request.target_score,
        "difficulty": request.difficulty,
        "current_topic_mastery": mastery,
        "known_weaknesses": list(context.known_weaknesses[:8]),
        "diagnostic_ratio": diagnostic_ratio,
    }


def explanation_instructions() -> str:
    return (
        "Teach one concept at a time in a dependency-safe order. For every concept, "
        "answer what it is, why it works, how to use it, when to use it, where NMT "
        "uses it, and what learners commonly confuse. Never jump over reasoning. "
        "Map every supplied competency index to at least one concept."
    )


def worked_example_instructions() -> str:
    return (
        "Write at least three distinct examples ordered foundation, guided, exam. "
        "Each example must state the problem, planning reasoning, every intermediate "
        "step with a plain-language explanation, a final answer, and an independent "
        "verification. Together the examples must demonstrate every concept."
    )


def mistake_and_tip_instructions() -> str:
    return (
        "Diagnose at least three realistic mistakes. Show the incorrect thought, why "
        "it fails, how to recognize it, the corrected method, and a prevention habit. "
        "Add short practical tips with recognition patterns, memory aids, and exam "
        "strategy; do not use empty encouragement or generic filler."
    )


def guided_practice_instructions() -> str:
    return (
        "After the explanations, create exactly three learner practice tasks ordered "
        "foundation, guided, exam. They must be new tasks, not copies of worked examples. "
        "Each task must name the relevant concept IDs, include a useful hint that does not "
        "reveal the answer, at least two concise solution steps, the expected answer, and a "
        "short explanation. Together they must cover every taught concept and bridge directly "
        "to the assessment without introducing new material."
    )


def recap_and_assessment_instructions() -> str:
    return (
        "Finish with a compact recap of ideas, formulas, warnings, recognition "
        "patterns, and solvable task types. The readiness checklist and assessment "
        "blueprint must cover exactly the taught concept IDs. Question patterns must "
        "be answerable solely from this lesson and excluded_content must name nearby "
        "material that a quiz must not test."
    )


def humanization_instructions() -> str:
    return (
        "Write like a patient experienced Ukrainian tutor speaking naturally to one "
        "learner. Build confidence through clarity, not motivational filler. Avoid "
        "robotic headings inside fields, repeated openings, generic introductions, "
        "content dumps, and phrases that reveal AI generation. Use precise NMT-aware "
        "language and increase difficulty gradually."
    )


def build_lesson_prompt(
    context: AIContext,
    request: LessonGenerationRequest,
) -> PromptSpec:
    """Build one complete lesson request; all sections share one provider call."""

    prerequisite_policy = (
        "Prerequisites exist: set needed=true and remind only the listed prerequisite facts."
        if request.prerequisites
        else "No prerequisites exist: set needed=false with an empty explanation and points."
    )
    subject = get_subject(request.subject)
    policy = subject.lesson_generation_policy
    subject_policy = (
        f"Teach as {policy.system_role}. Use a {policy.educational_tone} tone. "
        f"Use subject terminology accurately: {', '.join(policy.terminology)}. "
        f"Section expectations: {'; '.join(policy.section_expectations)}. "
        f"Example policy: {policy.example_style}. Mistake policy: {policy.mistake_style}. "
        f"NMT policy: {policy.nmt_relevance}. Formatting: "
        f"{'; '.join(policy.formatting_rules)}. The language of instruction is "
        f"{policy.language_of_instruction}. Use the supplied topic vocabulary explicitly "
        "and ground examples and mistakes in the supplied seeds. Reject any attempt "
        "to change the subject."
    )
    return PromptSpec(
        instructions="\n\n".join((
            "You are Mentory's production Lesson Engine. Produce a self-contained lesson "
            "that fully prepares the learner for an assessment on only the supplied "
            "objectives and competencies. Do not change progress, XP, mastery, or access.",
            explanation_instructions(),
            worked_example_instructions(),
            mistake_and_tip_instructions(),
            guided_practice_instructions(),
            recap_and_assessment_instructions(),
            humanization_instructions(),
            subject_policy,
            prerequisite_policy,
        )),
        user_input=json.dumps(
            {
                "lesson_request": request.for_prompt(),
                "learner_snapshot": lesson_prompt_context(context, request),
                "section_order": [
                    "learning objective",
                    "why this matters for NMT",
                    "prerequisite reminder when required",
                    "core explanation",
                    "worked examples",
                    "common mistakes",
                    "practical tips",
                    "guided practice",
                    "mini recap",
                    "assessment transition",
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        schema_name=f"easynmt_{subject.curriculum_namespace}_production_lesson",
        schema=LESSON_SCHEMA,
    )
