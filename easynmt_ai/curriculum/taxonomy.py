"""Versioned, application-owned subject taxonomies and graph validation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ..subjects import get_subject


ALLOWED_DIFFICULTIES = frozenset({"foundation", "intermediate", "advanced"})
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOPIC_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*\.[a-z0-9_]+\.[a-z0-9_]+$"
)
REQUIRED_TOPIC_FIELDS = frozenset({
    "subject",
    "id",
    "slug",
    "title_uk",
    "description_uk",
    "domain",
    "difficulty",
    "estimated_minutes",
    "prerequisite_topic_ids",
    "learning_objectives",
    "competencies",
    "required",
    "recommended_after_topic_ids",
})

MATH_TAXONOMY_FILE = Path(__file__).with_name("data") / "math_v1.json"

# The legacy UI catalog remains independent. This explicit bridge is the only
# place where its numeric lesson IDs are interpreted as canonical topics.
LEGACY_MATH_LESSON_TOPIC_MAP: Mapping[int, str] = {
    1: "math.algebra.quadratic_equations",
    2: "math.algebra.linear_equations",
    3: "math.functions.concept_graphs",
}


@dataclass(frozen=True)
class TaxonomyValidationIssue:
    code: str
    message: str
    topic_id: Optional[str] = None
    field: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "topic_id": self.topic_id,
            "field": self.field,
        }


@dataclass(frozen=True)
class TaxonomyTopic:
    subject: str
    id: str
    slug: str
    title_uk: str
    description_uk: str
    domain: str
    difficulty: str
    estimated_minutes: int
    prerequisite_topic_ids: tuple[str, ...]
    learning_objectives: tuple[str, ...]
    competencies: tuple[str, ...]
    required: bool
    recommended_after_topic_ids: tuple[str, ...]
    vocabulary: tuple[str, ...] = ()
    example_seeds: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
    assessment_focus: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaxonomyTopic":
        return cls(
            subject=str(data["subject"]),
            id=str(data["id"]),
            slug=str(data["slug"]),
            title_uk=str(data["title_uk"]),
            description_uk=str(data["description_uk"]),
            domain=str(data["domain"]),
            difficulty=str(data["difficulty"]),
            estimated_minutes=int(data["estimated_minutes"]),
            prerequisite_topic_ids=tuple(str(item) for item in data["prerequisite_topic_ids"]),
            learning_objectives=tuple(str(item) for item in data["learning_objectives"]),
            competencies=tuple(str(item) for item in data["competencies"]),
            required=bool(data["required"]),
            recommended_after_topic_ids=tuple(
                str(item) for item in data["recommended_after_topic_ids"]
            ),
            vocabulary=tuple(str(item) for item in data.get("vocabulary", ())),
            example_seeds=tuple(str(item) for item in data.get("example_seeds", ())),
            common_mistakes=tuple(str(item) for item in data.get("common_mistakes", ())),
            assessment_focus=tuple(
                str(item)
                for item in data.get("assessment_focus", data["competencies"])
            ),
        )

    def for_prompt(self) -> dict[str, Any]:
        return {
            "topic_id": self.id,
            "title_uk": self.title_uk,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "prerequisite_topic_ids": list(self.prerequisite_topic_ids),
            "objectives": list(self.learning_objectives),
            "competencies": list(self.competencies),
            "vocabulary": list(self.vocabulary),
            "example_seeds": list(self.example_seeds),
            "common_mistakes": list(self.common_mistakes),
            "assessment_focus": list(self.assessment_focus),
            "required": self.required,
        }


@dataclass(frozen=True)
class CurriculumTaxonomy:
    version: str
    subject: str
    completeness_note_uk: str
    topics: tuple[TaxonomyTopic, ...]

    @property
    def topics_by_id(self) -> dict[str, TaxonomyTopic]:
        return {topic.id: topic for topic in self.topics}

    def topic(self, topic_id: str) -> TaxonomyTopic:
        try:
            return self.topics_by_id[topic_id]
        except KeyError as exc:
            raise KeyError(f"Unknown taxonomy topic: {topic_id}") from exc

    def prerequisite_closure(self, topic_ids: Sequence[str]) -> set[str]:
        result: set[str] = set()
        topics = self.topics_by_id

        def visit(topic_id: str) -> None:
            if topic_id in result:
                return
            topic = topics[topic_id]
            for prerequisite_id in topic.prerequisite_topic_ids:
                visit(prerequisite_id)
            result.add(topic_id)

        for topic_id in topic_ids:
            visit(topic_id)
        return result

    def topological_order(
        self,
        topic_ids: Optional[Sequence[str]] = None,
        *,
        include_recommendations: bool = True,
    ) -> tuple[str, ...]:
        selected = set(topic_ids or self.topics_by_id)
        original_order = {topic.id: index for index, topic in enumerate(self.topics)}
        incoming = {topic_id: set() for topic_id in selected}
        outgoing = {topic_id: set() for topic_id in selected}
        for topic_id in selected:
            topic = self.topic(topic_id)
            dependencies = set(topic.prerequisite_topic_ids)
            if include_recommendations:
                dependencies.update(topic.recommended_after_topic_ids)
            for dependency in dependencies & selected:
                incoming[topic_id].add(dependency)
                outgoing[dependency].add(topic_id)

        ready = sorted(
            (topic_id for topic_id, dependencies in incoming.items() if not dependencies),
            key=original_order.get,
        )
        ordered: list[str] = []
        while ready:
            topic_id = ready.pop(0)
            ordered.append(topic_id)
            for dependent in sorted(outgoing[topic_id], key=original_order.get):
                incoming[dependent].discard(topic_id)
                if not incoming[dependent] and dependent not in ready:
                    ready.append(dependent)
                    ready.sort(key=original_order.get)
        if len(ordered) != len(selected):
            raise ValueError("Taxonomy ordering constraints contain a cycle")
        return tuple(ordered)


@dataclass(frozen=True)
class TaxonomyValidationResult:
    valid: bool
    issues: tuple[TaxonomyValidationIssue, ...] = field(default_factory=tuple)
    taxonomy: Optional[CurriculumTaxonomy] = None


class TaxonomyValidationError(ValueError):
    def __init__(self, result: TaxonomyValidationResult):
        self.result = result
        summary = "; ".join(issue.message for issue in result.issues[:5])
        super().__init__(summary or "Invalid mathematics taxonomy")


def _string_array(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _find_cycle(graph: Mapping[str, set[str]]) -> tuple[str, ...]:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> tuple[str, ...]:
        if node in visiting:
            start = visiting.index(node)
            return tuple(visiting[start:] + [node])
        if node in visited:
            return ()
        visiting.append(node)
        for dependency in graph.get(node, set()):
            cycle = visit(dependency)
            if cycle:
                return cycle
        visiting.pop()
        visited.add(node)
        return ()

    for node in graph:
        cycle = visit(node)
        if cycle:
            return cycle
    return ()


def validate_taxonomy_payload(
    payload: Mapping[str, Any],
    *,
    expected_subject: str | None = None,
) -> TaxonomyValidationResult:
    issues: list[TaxonomyValidationIssue] = []
    version = str(payload.get("version") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    completeness_note = str(payload.get("completeness_note_uk") or "").strip()
    raw_topics = payload.get("topics")
    if not version:
        issues.append(TaxonomyValidationIssue("missing_field", "Taxonomy version is required", field="version"))
    try:
        subject_definition = get_subject(subject)
    except KeyError:
        subject_definition = None
        issues.append(TaxonomyValidationIssue(
            "invalid_subject",
            "Taxonomy subject must be a registered EasyNMT subject",
            field="subject",
        ))
    if expected_subject is not None and subject != expected_subject:
        issues.append(TaxonomyValidationIssue(
            "invalid_subject",
            f"Taxonomy subject must be {expected_subject}",
            field="subject",
        ))
    if not completeness_note:
        issues.append(TaxonomyValidationIssue(
            "missing_field", "Taxonomy completeness note is required", field="completeness_note_uk"
        ))
    if not isinstance(raw_topics, Sequence) or isinstance(raw_topics, (str, bytes)) or not raw_topics:
        issues.append(TaxonomyValidationIssue("missing_topics", "Taxonomy topics must be a non-empty array"))
        return TaxonomyValidationResult(False, tuple(issues))

    valid_rows: list[Mapping[str, Any]] = []
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for index, raw_topic in enumerate(raw_topics):
        if not isinstance(raw_topic, Mapping):
            issues.append(TaxonomyValidationIssue(
                "invalid_topic", f"Topic at index {index} must be an object"
            ))
            continue
        topic_id = str(raw_topic.get("id") or "").strip() or None
        missing = sorted(REQUIRED_TOPIC_FIELDS - set(raw_topic))
        for field_name in missing:
            issues.append(TaxonomyValidationIssue(
                "missing_field",
                f"Topic {topic_id or index} is missing {field_name}",
                topic_id=topic_id,
                field=field_name,
            ))
        if missing:
            continue
        slug = str(raw_topic.get("slug") or "").strip()
        if topic_id in seen_ids:
            issues.append(TaxonomyValidationIssue(
                "duplicate_topic_id", f"Duplicate topic ID: {topic_id}", topic_id=topic_id, field="id"
            ))
        seen_ids.add(topic_id or "")
        if slug in seen_slugs:
            issues.append(TaxonomyValidationIssue(
                "duplicate_slug", f"Duplicate topic slug: {slug}", topic_id=topic_id, field="slug"
            ))
        seen_slugs.add(slug)
        if not topic_id or not TOPIC_ID_PATTERN.fullmatch(topic_id):
            issues.append(TaxonomyValidationIssue(
                "invalid_topic_id", f"Invalid topic ID: {topic_id}", topic_id=topic_id, field="id"
            ))
        elif subject_definition and not topic_id.startswith(
            f"{subject_definition.curriculum_namespace}."
        ):
            issues.append(TaxonomyValidationIssue(
                "invalid_topic_id",
                f"Topic ID {topic_id} is outside the subject namespace",
                topic_id=topic_id,
                field="id",
            ))
        if not SLUG_PATTERN.fullmatch(slug):
            issues.append(TaxonomyValidationIssue(
                "invalid_slug", f"Invalid topic slug: {slug}", topic_id=topic_id, field="slug"
            ))
        for field_name in ("subject", "title_uk", "description_uk", "domain", "difficulty"):
            if not isinstance(raw_topic.get(field_name), str) or not raw_topic[field_name].strip():
                issues.append(TaxonomyValidationIssue(
                    "invalid_field", f"Topic {topic_id} has invalid {field_name}", topic_id, field_name
                ))
        if raw_topic.get("subject") != subject:
            issues.append(TaxonomyValidationIssue(
                "invalid_subject", f"Topic {topic_id} subject does not match taxonomy", topic_id, "subject"
            ))
        if raw_topic.get("difficulty") not in ALLOWED_DIFFICULTIES:
            issues.append(TaxonomyValidationIssue(
                "invalid_difficulty", f"Topic {topic_id} has invalid difficulty", topic_id, "difficulty"
            ))
        try:
            estimated_minutes = int(raw_topic.get("estimated_minutes"))
            if not 15 <= estimated_minutes <= 600:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(TaxonomyValidationIssue(
                "invalid_duration", f"Topic {topic_id} has invalid study time", topic_id, "estimated_minutes"
            ))
        for field_name in (
            "prerequisite_topic_ids",
            "learning_objectives",
            "competencies",
            "recommended_after_topic_ids",
        ):
            if not _string_array(raw_topic.get(field_name)) and raw_topic.get(field_name) != []:
                issues.append(TaxonomyValidationIssue(
                    "invalid_field", f"Topic {topic_id} has invalid {field_name}", topic_id, field_name
                ))
        for field_name in (
            "vocabulary",
            "example_seeds",
            "common_mistakes",
            "assessment_focus",
        ):
            if field_name in raw_topic and not _string_array(raw_topic.get(field_name)):
                issues.append(TaxonomyValidationIssue(
                    "invalid_field",
                    f"Topic {topic_id} has invalid {field_name}",
                    topic_id,
                    field_name,
                ))
        if not raw_topic.get("learning_objectives"):
            issues.append(TaxonomyValidationIssue(
                "missing_objectives", f"Topic {topic_id} needs learning objectives", topic_id, "learning_objectives"
            ))
        if not raw_topic.get("competencies"):
            issues.append(TaxonomyValidationIssue(
                "missing_competencies", f"Topic {topic_id} needs competencies", topic_id, "competencies"
            ))
        if not isinstance(raw_topic.get("required"), bool):
            issues.append(TaxonomyValidationIssue(
                "invalid_required_flag", f"Topic {topic_id} required must be boolean", topic_id, "required"
            ))
        valid_rows.append(raw_topic)

    topic_ids = {str(row.get("id")) for row in valid_rows}
    prerequisite_graph: dict[str, set[str]] = {topic_id: set() for topic_id in topic_ids}
    ordering_graph: dict[str, set[str]] = {topic_id: set() for topic_id in topic_ids}
    for row in valid_rows:
        topic_id = str(row["id"])
        prerequisites = tuple(str(item) for item in row.get("prerequisite_topic_ids", ()))
        recommended = tuple(str(item) for item in row.get("recommended_after_topic_ids", ()))
        if len(set(prerequisites)) != len(prerequisites):
            issues.append(TaxonomyValidationIssue(
                "duplicate_prerequisite", f"Topic {topic_id} repeats a prerequisite", topic_id,
                "prerequisite_topic_ids",
            ))
        for dependency in prerequisites:
            if dependency == topic_id:
                issues.append(TaxonomyValidationIssue(
                    "self_dependency", f"Topic {topic_id} depends on itself", topic_id,
                    "prerequisite_topic_ids",
                ))
            elif dependency not in topic_ids:
                issues.append(TaxonomyValidationIssue(
                    "unknown_prerequisite", f"Topic {topic_id} has unknown prerequisite {dependency}",
                    topic_id, "prerequisite_topic_ids",
                ))
            else:
                prerequisite_graph[topic_id].add(dependency)
                ordering_graph[topic_id].add(dependency)
        for dependency in recommended:
            if dependency == topic_id:
                issues.append(TaxonomyValidationIssue(
                    "self_dependency", f"Topic {topic_id} recommends itself before itself", topic_id,
                    "recommended_after_topic_ids",
                ))
            elif dependency not in topic_ids:
                issues.append(TaxonomyValidationIssue(
                    "unknown_ordering_topic", f"Topic {topic_id} has unknown ordering topic {dependency}",
                    topic_id, "recommended_after_topic_ids",
                ))
            else:
                ordering_graph[topic_id].add(dependency)

    prerequisite_cycle = _find_cycle(prerequisite_graph)
    if prerequisite_cycle:
        issues.append(TaxonomyValidationIssue(
            "circular_dependency",
            "Circular prerequisite dependency: " + " -> ".join(prerequisite_cycle),
            topic_id=prerequisite_cycle[0],
        ))
    ordering_cycle = _find_cycle(ordering_graph)
    if ordering_cycle and not prerequisite_cycle:
        issues.append(TaxonomyValidationIssue(
            "impossible_ordering",
            "Recommended ordering is impossible: " + " -> ".join(ordering_cycle),
            topic_id=ordering_cycle[0],
        ))

    if issues:
        return TaxonomyValidationResult(False, tuple(issues))
    taxonomy = CurriculumTaxonomy(
        version=version,
        subject=subject,
        completeness_note_uk=completeness_note,
        topics=tuple(TaxonomyTopic.from_dict(row) for row in valid_rows),
    )
    return TaxonomyValidationResult(True, (), taxonomy)


def load_taxonomy(
    subject: str,
    path: Path | None = None,
) -> CurriculumTaxonomy:
    definition = get_subject(subject)
    taxonomy_path = path or Path(__file__).with_name("data") / definition.taxonomy_filename
    with taxonomy_path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    result = validate_taxonomy_payload(payload, expected_subject=subject)
    if not result.valid or result.taxonomy is None:
        raise TaxonomyValidationError(result)
    return result.taxonomy


def load_math_taxonomy(path: Path | None = None) -> CurriculumTaxonomy:
    """Compatibility wrapper for the original Task 2 public API."""

    return load_taxonomy("math", path)


# Compatibility alias retained for integrations built during Task 2.
MathTaxonomy = CurriculumTaxonomy


def map_legacy_completed_lessons(lesson_ids: Sequence[int]) -> tuple[str, ...]:
    return tuple(
        LEGACY_MATH_LESSON_TOPIC_MAP[lesson_id]
        for lesson_id in lesson_ids
        if lesson_id in LEGACY_MATH_LESSON_TOPIC_MAP
    )


def resolve_weakness_topic_ids(values: Sequence[str]) -> tuple[str, ...]:
    aliases = (
        (("fraction", "fractions", "дріб", "дроб"), "math.numbers.fractions"),
        (("percent", "відсот"), "math.numbers.percentages"),
        (("proportion", "пропорц"), "math.numbers.proportions"),
        (("quadratic", "квадратн"), "math.algebra.quadratic_equations"),
        (("linear equation", "лінійн", "рівнян"), "math.algebra.linear_equations"),
        (("function", "graph", "функц", "граф"), "math.functions.concept_graphs"),
        (("geometry", "геометр"), "math.geometry.triangles_angles"),
        (("trigon", "тригон"), "math.trigonometry.right_triangles"),
        (("probab", "ймовір"), "math.probability.basic_probability"),
        (("statistic", "статист"), "math.statistics.descriptive_statistics"),
    )
    resolved: list[str] = []
    for value in values:
        normalized = str(value or "").casefold()
        for terms, topic_id in aliases:
            if any(term in normalized for term in terms) and topic_id not in resolved:
                resolved.append(topic_id)
    return tuple(resolved)
