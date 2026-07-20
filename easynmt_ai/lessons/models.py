"""Typed, quiz-ready educational content for production lessons."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..models import (
    AIModelValidationError,
    SerializableAIModel,
    _boolean,
    _integer,
    _mapping,
    _number,
    _strings,
    _text,
    _timestamp,
)


LESSON_SECTION_ORDER = (
    "learning_objective",
    "nmt_relevance",
    "prerequisite_reminder",
    "core_explanation",
    "worked_examples",
    "common_mistakes",
    "practical_tips",
    "mini_recap",
    "assessment_transition",
)


def _object_array(value: object, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise AIModelValidationError(f"{name} must be an array")
    return tuple(_mapping(item, f"{name} item") for item in value)


@dataclass(frozen=True)
class LessonPrerequisite(SerializableAIModel):
    topic_id: str
    title: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonPrerequisite":
        data = _mapping(value, "lesson prerequisite")
        return cls(
            topic_id=_text(data.get("topic_id"), "lesson_prerequisite.topic_id"),
            title=_text(data.get("title"), "lesson_prerequisite.title"),
        )


@dataclass(frozen=True)
class LessonGenerationRequest(SerializableAIModel):
    """Authoritative curriculum and taxonomy input to lesson generation."""

    lesson_id: str
    curriculum_id: str
    curriculum_unit_id: str
    topic_id: str
    subject: str
    title: str
    description: str
    objectives: tuple[str, ...]
    competencies: tuple[str, ...]
    prerequisites: tuple[LessonPrerequisite, ...]
    difficulty: str
    estimated_minutes: int
    mastery_target: float
    target_score: int
    language: str = "uk"
    topic_vocabulary: tuple[str, ...] = ()
    example_seeds: tuple[str, ...] = ()
    common_mistake_seeds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "lesson_id",
            "curriculum_id",
            "curriculum_unit_id",
            "topic_id",
            "subject",
            "title",
            "description",
            "difficulty",
            "language",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AIModelValidationError(f"lesson {field_name} must not be empty")
        if not self.objectives or not self.competencies:
            raise AIModelValidationError(
                "lesson generation requires objectives and competencies"
            )
        if len(set(self.objectives)) != len(self.objectives):
            raise AIModelValidationError("lesson objectives must be unique")
        if len(set(self.competencies)) != len(self.competencies):
            raise AIModelValidationError("lesson competencies must be unique")
        if not 0.0 <= float(self.mastery_target) <= 1.0:
            raise AIModelValidationError("lesson mastery target is out of range")
        if (
            isinstance(self.estimated_minutes, bool)
            or not isinstance(self.estimated_minutes, int)
            or self.estimated_minutes < 1
        ):
            raise AIModelValidationError("lesson estimated minutes is invalid")
        if (
            isinstance(self.target_score, bool)
            or not isinstance(self.target_score, int)
            or not 100 <= self.target_score <= 200
        ):
            raise AIModelValidationError("lesson target score is out of range")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonGenerationRequest":
        data = _mapping(value, "lesson generation request")
        prerequisites = tuple(
            LessonPrerequisite.from_dict(item)
            for item in _object_array(data.get("prerequisites", ()), "lesson prerequisites")
        )
        return cls(
            lesson_id=_text(data.get("lesson_id"), "lesson_request.lesson_id"),
            curriculum_id=_text(data.get("curriculum_id"), "lesson_request.curriculum_id"),
            curriculum_unit_id=_text(
                data.get("curriculum_unit_id"),
                "lesson_request.curriculum_unit_id",
            ),
            topic_id=_text(data.get("topic_id"), "lesson_request.topic_id"),
            subject=_text(data.get("subject"), "lesson_request.subject"),
            title=_text(data.get("title"), "lesson_request.title"),
            description=_text(data.get("description"), "lesson_request.description"),
            objectives=_strings(data.get("objectives"), "lesson_request.objectives"),
            competencies=_strings(
                data.get("competencies"),
                "lesson_request.competencies",
            ),
            prerequisites=prerequisites,
            difficulty=_text(data.get("difficulty"), "lesson_request.difficulty"),
            estimated_minutes=_integer(
                data.get("estimated_minutes"),
                "lesson_request.estimated_minutes",
                minimum=1,
            ),
            mastery_target=_number(
                data.get("mastery_target"),
                "lesson_request.mastery_target",
                minimum=0,
                maximum=1,
            ),
            target_score=_integer(
                data.get("target_score"),
                "lesson_request.target_score",
                minimum=100,
            ),
            language=_text(data.get("language", "uk"), "lesson_request.language"),
            topic_vocabulary=_strings(
                data.get("topic_vocabulary", ()),
                "lesson_request.topic_vocabulary",
            ),
            example_seeds=_strings(
                data.get("example_seeds", ()),
                "lesson_request.example_seeds",
            ),
            common_mistake_seeds=_strings(
                data.get("common_mistake_seeds", ()),
                "lesson_request.common_mistake_seeds",
            ),
        )

    @classmethod
    def from_learning_plan(cls, context, plan) -> "LessonGenerationRequest":
        """Compatibility adapter for the Task 1 engine interface."""

        prerequisites = tuple(
            LessonPrerequisite(topic_id=item, title=item)
            for item in plan.prerequisite_ids
        )
        return cls(
            lesson_id=plan.id,
            curriculum_id=context.active_curriculum_id or "contract-curriculum",
            curriculum_unit_id=plan.id,
            topic_id=f"{context.subject}.contract.{plan.id}",
            subject=context.subject,
            title=plan.title,
            description=plan.objective,
            objectives=(plan.objective,),
            competencies=(plan.objective,),
            prerequisites=prerequisites,
            difficulty=plan.difficulty,
            estimated_minutes=plan.estimated_minutes,
            mastery_target=0.75,
            target_score=context.goal_score or 170,
            language=context.language,
        )

    def for_prompt(self) -> dict[str, Any]:
        """Return educational inputs only; opaque ownership IDs stay local."""

        result = {
            "topic_id": self.topic_id,
            "subject": self.subject,
            "title": self.title,
            "description": self.description,
            "objectives": list(self.objectives),
            "competencies": [
                {"index": index, "description": value}
                for index, value in enumerate(self.competencies, 1)
            ],
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "mastery_target": self.mastery_target,
            "target_score": self.target_score,
            "language": self.language,
        }
        if self.topic_vocabulary:
            result["topic_vocabulary"] = list(self.topic_vocabulary)
        if self.example_seeds:
            result["example_seeds"] = list(self.example_seeds)
        if self.common_mistake_seeds:
            result["common_mistake_seeds"] = list(self.common_mistake_seeds)
        return result


@dataclass(frozen=True)
class LessonPrerequisiteReminder(SerializableAIModel):
    needed: bool
    explanation: str
    points: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonPrerequisiteReminder":
        data = _mapping(value, "prerequisite reminder")
        return cls(
            needed=_boolean(data.get("needed"), "prerequisite_reminder.needed"),
            explanation=_text(
                data.get("explanation", ""),
                "prerequisite_reminder.explanation",
                allow_empty=True,
            ),
            points=_strings(data.get("points", ()), "prerequisite_reminder.points"),
        )


@dataclass(frozen=True)
class LessonConcept(SerializableAIModel):
    id: str
    title: str
    what: str
    why: str
    how: str
    when_used: str
    nmt_use: str
    common_confusion: str
    competency_indices: tuple[int, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonConcept":
        data = _mapping(value, "lesson concept")
        raw_indices = data.get("competency_indices", ())
        if not isinstance(raw_indices, Sequence) or isinstance(raw_indices, (str, bytes)):
            raise AIModelValidationError("concept competency indices must be an array")
        indices = tuple(
            _integer(item, "concept.competency_indices item", minimum=1)
            for item in raw_indices
        )
        return cls(
            id=_text(data.get("id"), "concept.id"),
            title=_text(data.get("title"), "concept.title"),
            what=_text(data.get("what"), "concept.what"),
            why=_text(data.get("why"), "concept.why"),
            how=_text(data.get("how"), "concept.how"),
            when_used=_text(data.get("when_used"), "concept.when_used"),
            nmt_use=_text(data.get("nmt_use"), "concept.nmt_use"),
            common_confusion=_text(
                data.get("common_confusion"),
                "concept.common_confusion",
            ),
            competency_indices=indices,
        )


@dataclass(frozen=True)
class WorkedExampleStep(SerializableAIModel):
    order: int
    work: str
    explanation: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkedExampleStep":
        data = _mapping(value, "worked example step")
        return cls(
            order=_integer(data.get("order"), "example_step.order", minimum=1),
            work=_text(data.get("work"), "example_step.work"),
            explanation=_text(data.get("explanation"), "example_step.explanation"),
        )


@dataclass(frozen=True)
class WorkedExample(SerializableAIModel):
    id: str
    difficulty: str
    problem: str
    reasoning: str
    concept_ids: tuple[str, ...]
    steps: tuple[WorkedExampleStep, ...]
    final_answer: str
    verification: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkedExample":
        data = _mapping(value, "worked example")
        steps = tuple(
            WorkedExampleStep.from_dict(item)
            for item in _object_array(data.get("steps"), "worked example steps")
        )
        return cls(
            id=_text(data.get("id"), "worked_example.id"),
            difficulty=_text(data.get("difficulty"), "worked_example.difficulty"),
            problem=_text(data.get("problem"), "worked_example.problem"),
            reasoning=_text(data.get("reasoning"), "worked_example.reasoning"),
            concept_ids=_strings(
                data.get("concept_ids"),
                "worked_example.concept_ids",
            ),
            steps=steps,
            final_answer=_text(
                data.get("final_answer"),
                "worked_example.final_answer",
            ),
            verification=_text(data.get("verification"), "worked_example.verification"),
        )


@dataclass(frozen=True)
class LessonCommonMistake(SerializableAIModel):
    id: str
    incorrect_reasoning: str
    why_incorrect: str
    recognition: str
    correction: str
    prevention: str
    concept_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonCommonMistake":
        data = _mapping(value, "common mistake")
        return cls(
            id=_text(data.get("id"), "common_mistake.id"),
            incorrect_reasoning=_text(
                data.get("incorrect_reasoning"),
                "common_mistake.incorrect_reasoning",
            ),
            why_incorrect=_text(
                data.get("why_incorrect"),
                "common_mistake.why_incorrect",
            ),
            recognition=_text(data.get("recognition"), "common_mistake.recognition"),
            correction=_text(data.get("correction"), "common_mistake.correction"),
            prevention=_text(data.get("prevention"), "common_mistake.prevention"),
            concept_ids=_strings(data.get("concept_ids"), "common_mistake.concept_ids"),
        )


@dataclass(frozen=True)
class LessonPracticalTip(SerializableAIModel):
    id: str
    advice: str
    use_when: str
    recognition_pattern: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonPracticalTip":
        data = _mapping(value, "practical tip")
        return cls(
            id=_text(data.get("id"), "practical_tip.id"),
            advice=_text(data.get("advice"), "practical_tip.advice"),
            use_when=_text(data.get("use_when"), "practical_tip.use_when"),
            recognition_pattern=_text(
                data.get("recognition_pattern"),
                "practical_tip.recognition_pattern",
            ),
        )


@dataclass(frozen=True)
class LessonRecap(SerializableAIModel):
    main_ideas: tuple[str, ...]
    formulas: tuple[str, ...]
    warnings: tuple[str, ...]
    recognition_patterns: tuple[str, ...]
    can_solve: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonRecap":
        data = _mapping(value, "lesson recap")
        return cls(
            main_ideas=_strings(data.get("main_ideas"), "recap.main_ideas"),
            formulas=_strings(data.get("formulas"), "recap.formulas"),
            warnings=_strings(data.get("warnings"), "recap.warnings"),
            recognition_patterns=_strings(
                data.get("recognition_patterns"),
                "recap.recognition_patterns",
            ),
            can_solve=_strings(data.get("can_solve"), "recap.can_solve"),
        )


@dataclass(frozen=True)
class LessonAssessmentTransition(SerializableAIModel):
    message: str
    readiness_checklist: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonAssessmentTransition":
        data = _mapping(value, "assessment transition")
        return cls(
            message=_text(data.get("message"), "assessment_transition.message"),
            readiness_checklist=_strings(
                data.get("readiness_checklist"),
                "assessment_transition.readiness_checklist",
            ),
        )


@dataclass(frozen=True)
class LessonAssessmentBlueprint(SerializableAIModel):
    covered_concept_ids: tuple[str, ...]
    question_patterns: tuple[str, ...]
    required_reasoning: tuple[str, ...]
    excluded_content: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonAssessmentBlueprint":
        data = _mapping(value, "assessment blueprint")
        return cls(
            covered_concept_ids=_strings(
                data.get("covered_concept_ids"),
                "assessment_blueprint.covered_concept_ids",
            ),
            question_patterns=_strings(
                data.get("question_patterns"),
                "assessment_blueprint.question_patterns",
            ),
            required_reasoning=_strings(
                data.get("required_reasoning"),
                "assessment_blueprint.required_reasoning",
            ),
            excluded_content=_strings(
                data.get("excluded_content", ()),
                "assessment_blueprint.excluded_content",
            ),
        )


@dataclass(frozen=True)
class LessonGenerationMetadata(SerializableAIModel):
    source: str
    request_fingerprint: str
    prompt_version: str
    schema_version: str
    model_identifier: str
    generated_at: str
    provider_response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LessonGenerationMetadata":
        data = _mapping(value, "lesson generation metadata")

        def optional_integer(name: str) -> int | None:
            raw = data.get(name)
            return None if raw is None else _integer(raw, f"lesson_metadata.{name}")

        response_id = str(data.get("provider_response_id") or "").strip() or None
        return cls(
            source=_text(data.get("source"), "lesson_metadata.source"),
            request_fingerprint=_text(
                data.get("request_fingerprint"),
                "lesson_metadata.request_fingerprint",
            ),
            prompt_version=_text(
                data.get("prompt_version"),
                "lesson_metadata.prompt_version",
            ),
            schema_version=_text(
                data.get("schema_version"),
                "lesson_metadata.schema_version",
            ),
            model_identifier=_text(
                data.get("model_identifier"),
                "lesson_metadata.model_identifier",
            ),
            generated_at=_timestamp(data.get("generated_at"), "lesson_metadata.generated_at"),
            provider_response_id=response_id,
            input_tokens=optional_integer("input_tokens"),
            output_tokens=optional_integer("output_tokens"),
            total_tokens=optional_integer("total_tokens"),
        )


@dataclass(frozen=True)
class Lesson(SerializableAIModel):
    """Immutable teaching artifact and structured Task 3C input."""

    id: str
    curriculum_id: str
    curriculum_unit_id: str
    topic_id: str
    title: str
    subject: str
    difficulty: str
    estimated_minutes: int
    objective_overview: str
    objectives: tuple[str, ...]
    competencies: tuple[str, ...]
    nmt_relevance: str
    nmt_task_types: tuple[str, ...]
    prerequisite_reminder: LessonPrerequisiteReminder
    concepts: tuple[LessonConcept, ...]
    worked_examples: tuple[WorkedExample, ...]
    common_mistakes: tuple[LessonCommonMistake, ...]
    practical_tips: tuple[LessonPracticalTip, ...]
    recap: LessonRecap
    assessment_transition: LessonAssessmentTransition
    assessment_blueprint: LessonAssessmentBlueprint
    generation_metadata: LessonGenerationMetadata

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Lesson":
        data = _mapping(value, "lesson")
        return cls(
            id=_text(data.get("id"), "lesson.id"),
            curriculum_id=_text(data.get("curriculum_id"), "lesson.curriculum_id"),
            curriculum_unit_id=_text(
                data.get("curriculum_unit_id"),
                "lesson.curriculum_unit_id",
            ),
            topic_id=_text(data.get("topic_id"), "lesson.topic_id"),
            title=_text(data.get("title"), "lesson.title"),
            subject=_text(data.get("subject"), "lesson.subject"),
            difficulty=_text(data.get("difficulty"), "lesson.difficulty"),
            estimated_minutes=_integer(
                data.get("estimated_minutes"),
                "lesson.estimated_minutes",
                minimum=1,
            ),
            objective_overview=_text(
                data.get("objective_overview"),
                "lesson.objective_overview",
            ),
            objectives=_strings(data.get("objectives"), "lesson.objectives"),
            competencies=_strings(data.get("competencies"), "lesson.competencies"),
            nmt_relevance=_text(data.get("nmt_relevance"), "lesson.nmt_relevance"),
            nmt_task_types=_strings(
                data.get("nmt_task_types"),
                "lesson.nmt_task_types",
            ),
            prerequisite_reminder=LessonPrerequisiteReminder.from_dict(
                _mapping(data.get("prerequisite_reminder"), "prerequisite reminder")
            ),
            concepts=tuple(
                LessonConcept.from_dict(item)
                for item in _object_array(data.get("concepts"), "lesson concepts")
            ),
            worked_examples=tuple(
                WorkedExample.from_dict(item)
                for item in _object_array(
                    data.get("worked_examples"),
                    "lesson worked examples",
                )
            ),
            common_mistakes=tuple(
                LessonCommonMistake.from_dict(item)
                for item in _object_array(
                    data.get("common_mistakes"),
                    "lesson common mistakes",
                )
            ),
            practical_tips=tuple(
                LessonPracticalTip.from_dict(item)
                for item in _object_array(
                    data.get("practical_tips"),
                    "lesson practical tips",
                )
            ),
            recap=LessonRecap.from_dict(_mapping(data.get("recap"), "lesson recap")),
            assessment_transition=LessonAssessmentTransition.from_dict(
                _mapping(data.get("assessment_transition"), "assessment transition")
            ),
            assessment_blueprint=LessonAssessmentBlueprint.from_dict(
                _mapping(data.get("assessment_blueprint"), "assessment blueprint")
            ),
            generation_metadata=LessonGenerationMetadata.from_dict(
                _mapping(data.get("generation_metadata"), "lesson generation metadata")
            ),
        )

    @property
    def section_order(self) -> tuple[str, ...]:
        return LESSON_SECTION_ORDER

    # Compatibility properties for Task 1 callers. New code should consume the
    # structured fields or ``for_quiz`` instead.
    @property
    def objective(self) -> str:
        return self.objective_overview

    @property
    def explanation(self) -> str:
        return "\n\n".join(f"{item.title}: {item.what} {item.how}" for item in self.concepts)

    @property
    def examples(self) -> tuple[str, ...]:
        return tuple(item.problem for item in self.worked_examples)

    @property
    def practice_tasks(self) -> tuple[str, ...]:
        return self.assessment_blueprint.question_patterns

    @property
    def summary(self) -> str:
        return " ".join(self.recap.main_ideas)

    def for_quiz(self) -> dict[str, Any]:
        """Return structured taught content without persistence metadata."""

        return {
            "lesson_id": self.id,
            "curriculum_unit_id": self.curriculum_unit_id,
            "topic_id": self.topic_id,
            "title": self.title,
            "subject": self.subject,
            "difficulty": self.difficulty,
            "objectives": list(self.objectives),
            "competencies": list(self.competencies),
            "concepts": [item.to_dict() for item in self.concepts],
            "worked_examples": [item.to_dict() for item in self.worked_examples],
            "common_mistakes": [item.to_dict() for item in self.common_mistakes],
            "recap": self.recap.to_dict(),
            "assessment_blueprint": self.assessment_blueprint.to_dict(),
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Return learner-facing content without provider/cache metadata."""

        return {
            "id": self.id,
            "curriculum_unit_id": self.curriculum_unit_id,
            "topic_id": self.topic_id,
            "title": self.title,
            "subject": self.subject,
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "section_order": list(self.section_order),
            "objective_overview": self.objective_overview,
            "objectives": list(self.objectives),
            "competencies": list(self.competencies),
            "nmt_relevance": self.nmt_relevance,
            "nmt_task_types": list(self.nmt_task_types),
            "prerequisite_reminder": self.prerequisite_reminder.to_dict(),
            "concepts": [item.to_dict() for item in self.concepts],
            "worked_examples": [item.to_dict() for item in self.worked_examples],
            "common_mistakes": [item.to_dict() for item in self.common_mistakes],
            "practical_tips": [item.to_dict() for item in self.practical_tips],
            "recap": self.recap.to_dict(),
            "assessment_transition": self.assessment_transition.to_dict(),
            "assessment_blueprint": self.assessment_blueprint.to_dict(),
        }
