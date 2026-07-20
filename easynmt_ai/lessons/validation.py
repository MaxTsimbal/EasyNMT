"""Deterministic completeness and curriculum-alignment checks for lessons."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..subjects import get_subject
from .models import Lesson, LessonGenerationRequest


@dataclass(frozen=True)
class LessonValidationIssue:
    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True)
class LessonValidationResult:
    valid: bool
    issues: tuple[LessonValidationIssue, ...] = field(default_factory=tuple)


def _normalized_duplicates(values: Iterable[str]) -> bool:
    normalized = [" ".join(str(value).casefold().split()) for value in values]
    return len(normalized) != len(set(normalized))


def _educational_text(lesson: Lesson) -> str:
    """Flatten provider-authored fields without authoritative local identity data."""

    values = [
        lesson.objective_overview,
        lesson.nmt_relevance,
        *lesson.nmt_task_types,
        lesson.prerequisite_reminder.explanation,
        *lesson.prerequisite_reminder.points,
        *(value for item in lesson.concepts for value in (
            item.title,
            item.what,
            item.why,
            item.how,
            item.when_used,
            item.nmt_use,
            item.common_confusion,
        )),
        *(value for item in lesson.worked_examples for value in (
            item.problem,
            item.reasoning,
            item.final_answer,
            item.verification,
        )),
        *(value for item in lesson.worked_examples for step in item.steps for value in (
            step.work,
            step.explanation,
        )),
        *(value for item in lesson.common_mistakes for value in (
            item.incorrect_reasoning,
            item.why_incorrect,
            item.recognition,
            item.correction,
            item.prevention,
        )),
        *(value for item in lesson.practical_tips for value in (
            item.advice,
            item.use_when,
            item.recognition_pattern,
        )),
        *lesson.recap.main_ideas,
        *lesson.recap.formulas,
        *lesson.recap.warnings,
        *lesson.recap.recognition_patterns,
        *lesson.recap.can_solve,
        lesson.assessment_transition.message,
        *lesson.assessment_transition.readiness_checklist,
        *lesson.assessment_blueprint.question_patterns,
        *lesson.assessment_blueprint.required_reasoning,
        *lesson.assessment_blueprint.excluded_content,
    ]
    return " ".join(str(value).casefold() for value in values if value)


def validate_lesson(
    lesson: Lesson,
    request: LessonGenerationRequest,
) -> LessonValidationResult:
    """Reject structurally valid but educationally incomplete lesson output."""

    issues: list[LessonValidationIssue] = []

    def add(code: str, message: str, field: str | None = None) -> None:
        issues.append(LessonValidationIssue(code, message, field))

    identity_fields = {
        "id": (lesson.id, request.lesson_id),
        "curriculum_id": (lesson.curriculum_id, request.curriculum_id),
        "curriculum_unit_id": (
            lesson.curriculum_unit_id,
            request.curriculum_unit_id,
        ),
        "topic_id": (lesson.topic_id, request.topic_id),
        "subject": (lesson.subject, request.subject),
        "title": (lesson.title, request.title),
        "difficulty": (lesson.difficulty, request.difficulty),
        "objectives": (lesson.objectives, request.objectives),
        "competencies": (lesson.competencies, request.competencies),
    }
    for field_name, (actual, expected) in identity_fields.items():
        if actual != expected:
            add(
                "authoritative_field_mismatch",
                f"Lesson {field_name} does not match the curriculum request.",
                field_name,
            )
    if lesson.estimated_minutes != request.estimated_minutes:
        add(
            "authoritative_field_mismatch",
            "Lesson duration does not match the curriculum unit.",
            "estimated_minutes",
        )

    try:
        subject_definition = get_subject(request.subject)
    except KeyError:
        add("unknown_subject", "Lesson subject is not registered.", "subject")
    else:
        if not request.topic_id.startswith(
            f"{subject_definition.curriculum_namespace}."
        ):
            add(
                "topic_subject_mismatch",
                "Lesson topic is outside the selected subject namespace.",
                "topic_id",
            )
        educational_text = _educational_text(lesson)
        profile = subject_definition.validation_profile
        positive_count = sum(
            marker.casefold() in educational_text
            for marker in profile.positive_markers
        )
        if positive_count < profile.minimum_positive_markers:
            add(
                "subject_alignment_missing",
                "Lesson content does not contain sufficient selected-subject evidence.",
                "content",
            )
        foreign_markers = tuple(
            marker
            for marker in profile.foreign_subject_markers
            if marker.casefold() in educational_text
        )
        if foreign_markers:
            add(
                "wrong_subject_content",
                "Lesson content contains material from another subject.",
                "content",
            )
        if request.topic_vocabulary and not any(
            marker.casefold() in educational_text
            for marker in request.topic_vocabulary
        ):
            add(
                "topic_alignment_missing",
                "Lesson content does not use the curriculum topic vocabulary.",
                "content",
            )

    if len(lesson.objective_overview) < 40:
        add("objective_too_short", "Learning objective is not explanatory enough.")
    if len(lesson.nmt_relevance) < 60 or len(lesson.nmt_task_types) < 2:
        add("nmt_relevance_incomplete", "NMT relevance must name practical task uses.")

    reminder = lesson.prerequisite_reminder
    prerequisites_required = bool(request.prerequisites)
    if reminder.needed != prerequisites_required:
        add(
            "prerequisite_policy_mismatch",
            "Prerequisite reminder does not match the curriculum prerequisites.",
        )
    if prerequisites_required and (
        len(reminder.explanation) < 30 or len(reminder.points) < 2
    ):
        add(
            "prerequisite_reminder_incomplete",
            "Required prerequisite reminder is not sufficient.",
        )
    if not prerequisites_required and (reminder.explanation or reminder.points):
        add(
            "unnecessary_prerequisite_content",
            "A root topic must not invent prerequisite material.",
        )

    if len(lesson.concepts) < 2:
        add("too_few_concepts", "A lesson must teach at least two progressive concepts.")
    concept_ids = [item.id for item in lesson.concepts]
    if len(concept_ids) != len(set(concept_ids)):
        add("duplicate_concept_id", "Concept IDs must be unique.")
    if _normalized_duplicates(item.title for item in lesson.concepts):
        add("duplicate_concept", "Concepts must not repeat the same material.")

    expected_competencies = set(range(1, len(request.competencies) + 1))
    covered_competencies: set[int] = set()
    for concept in lesson.concepts:
        if any(
            len(value) < minimum
            for value, minimum in (
                (concept.what, 35),
                (concept.why, 25),
                (concept.how, 45),
                (concept.when_used, 25),
                (concept.nmt_use, 25),
                (concept.common_confusion, 25),
            )
        ):
            add(
                "concept_explanation_incomplete",
                f"Concept {concept.id} does not answer every teaching question.",
                concept.id,
            )
        indices = set(concept.competency_indices)
        if not indices or not indices <= expected_competencies:
            add(
                "invalid_competency_reference",
                f"Concept {concept.id} references an invalid competency.",
                concept.id,
            )
        covered_competencies.update(indices)
    if covered_competencies != expected_competencies:
        add(
            "competency_coverage_incomplete",
            "Concepts must cover every authoritative curriculum competency.",
        )

    if len(lesson.worked_examples) < 3:
        add("too_few_examples", "A complete lesson requires at least three examples.")
    example_ids = [item.id for item in lesson.worked_examples]
    if len(example_ids) != len(set(example_ids)):
        add("duplicate_example_id", "Worked example IDs must be unique.")
    if _normalized_duplicates(item.problem for item in lesson.worked_examples):
        add("duplicate_example", "Worked examples must use distinct problems.")
    difficulty_order = {"foundation": 0, "guided": 1, "exam": 2}
    ranks: list[int] = []
    covered_concepts: set[str] = set()
    valid_concept_ids = set(concept_ids)
    for example in lesson.worked_examples:
        rank = difficulty_order.get(example.difficulty)
        if rank is None:
            add(
                "invalid_example_difficulty",
                f"Example {example.id} has an unsupported difficulty stage.",
                example.id,
            )
        else:
            ranks.append(rank)
        if len(example.reasoning) < 35 or len(example.verification) < 20:
            add(
                "example_reasoning_incomplete",
                f"Example {example.id} lacks reasoning or verification.",
                example.id,
            )
        if len(example.steps) < 2:
            add(
                "example_steps_incomplete",
                f"Example {example.id} must show intermediate steps.",
                example.id,
            )
        if [step.order for step in example.steps] != list(range(1, len(example.steps) + 1)):
            add(
                "example_step_order_invalid",
                f"Example {example.id} step order is not contiguous.",
                example.id,
            )
        if any(len(step.explanation) < 20 for step in example.steps):
            add(
                "example_step_unexplained",
                f"Example {example.id} contains an unexplained step.",
                example.id,
            )
        references = set(example.concept_ids)
        if not references or not references <= valid_concept_ids:
            add(
                "invalid_example_concept",
                f"Example {example.id} references unknown lesson concepts.",
                example.id,
            )
        covered_concepts.update(references)
    if ranks and (ranks != sorted(ranks) or ranks[0] != 0 or ranks[-1] != 2):
        add(
            "example_progression_invalid",
            "Examples must progress from foundation through an exam-level example.",
        )
    if valid_concept_ids and covered_concepts != valid_concept_ids:
        add(
            "example_coverage_incomplete",
            "Worked examples must demonstrate every lesson concept.",
        )

    if len(lesson.common_mistakes) < 3:
        add("too_few_mistakes", "A lesson requires at least three concrete mistakes.")
    mistake_ids = [item.id for item in lesson.common_mistakes]
    if len(mistake_ids) != len(set(mistake_ids)):
        add("duplicate_mistake_id", "Common mistake IDs must be unique.")
    for mistake in lesson.common_mistakes:
        if not set(mistake.concept_ids) <= valid_concept_ids:
            add(
                "invalid_mistake_concept",
                f"Mistake {mistake.id} references an unknown concept.",
                mistake.id,
            )
        if any(
            len(value) < 20
            for value in (
                mistake.incorrect_reasoning,
                mistake.why_incorrect,
                mistake.recognition,
                mistake.correction,
                mistake.prevention,
            )
        ):
            add(
                "mistake_explanation_incomplete",
                f"Mistake {mistake.id} is not fully diagnosed and corrected.",
                mistake.id,
            )

    if len(lesson.practical_tips) < 3:
        add("too_few_tips", "A lesson requires practical recognition and exam tips.")
    tip_ids = [item.id for item in lesson.practical_tips]
    if len(tip_ids) != len(set(tip_ids)):
        add("duplicate_tip_id", "Practical tip IDs must be unique.")

    recap_groups = {
        "main_ideas": lesson.recap.main_ideas,
        "formulas": lesson.recap.formulas,
        "warnings": lesson.recap.warnings,
        "recognition_patterns": lesson.recap.recognition_patterns,
        "can_solve": lesson.recap.can_solve,
    }
    for field_name, values in recap_groups.items():
        minimum = 1 if field_name == "formulas" else 2
        if len(values) < minimum:
            add(
                "recap_incomplete",
                f"Recap field {field_name} is incomplete.",
                field_name,
            )
        if _normalized_duplicates(values):
            add(
                "recap_repetition",
                f"Recap field {field_name} repeats content.",
                field_name,
            )

    if len(lesson.assessment_transition.message) < 40:
        add(
            "assessment_transition_incomplete",
            "Assessment transition must explain what comes next.",
        )
    if len(lesson.assessment_transition.readiness_checklist) < 4:
        add(
            "readiness_checklist_incomplete",
            "Assessment readiness requires at least four concrete checks.",
        )

    blueprint = lesson.assessment_blueprint
    if set(blueprint.covered_concept_ids) != valid_concept_ids:
        add(
            "blueprint_coverage_invalid",
            "Assessment blueprint must cover exactly the taught concepts.",
        )
    if len(blueprint.question_patterns) < 4:
        add(
            "blueprint_patterns_incomplete",
            "Assessment blueprint needs at least four question patterns.",
        )
    if len(blueprint.required_reasoning) < 2:
        add(
            "blueprint_reasoning_incomplete",
            "Assessment blueprint must state required reasoning skills.",
        )

    return LessonValidationResult(not issues, tuple(issues))
