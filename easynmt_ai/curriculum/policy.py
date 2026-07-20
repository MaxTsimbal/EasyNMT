"""Deterministic curriculum selection, validation, and regeneration policy."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from ..cache import build_cache_key
from ..models import Curriculum
from ..schemas import AIContext
from .taxonomy import (
    MathTaxonomy,
    map_legacy_completed_lessons,
    resolve_weakness_topic_ids,
)


ALLOWED_PRIORITIES = frozenset({"critical", "high", "normal", "review"})
ALLOWED_UNIT_REASONS = frozenset({
    "unmet_prerequisite",
    "core_for_target",
    "known_weakness",
    "review_mastered",
    "advanced_target",
    "diagnostic_gap",
})
ALLOWED_CHECKPOINT_REASONS = frozenset({
    "periodic_review",
    "weakness_review",
    "final_review",
})
GENERATION_REASONS = frozenset({
    "initial_diagnostic",
    "target_score_changed",
    "repeated_prerequisite_failure",
    "major_mastery_update",
    "curriculum_completed",
    "manual_request",
    "taxonomy_updated",
})


@dataclass(frozen=True)
class CurriculumPolicy:
    target_score: int
    starting_level: str
    required_topic_ids: tuple[str, ...]
    allowed_topic_ids: tuple[str, ...]
    mastered_topic_ids: tuple[str, ...]
    weakness_topic_ids: tuple[str, ...]
    review_topic_ids: tuple[str, ...]
    mastery_target: float
    max_session_minutes: int
    study_minutes_per_week: int
    available_weeks: Optional[int]

    def for_prompt(self) -> dict[str, Any]:
        return {
            "target_score": self.target_score,
            "starting_level": self.starting_level,
            "required_topic_ids": list(self.required_topic_ids),
            "allowed_topic_ids": list(self.allowed_topic_ids),
            "mastered_topic_ids": list(self.mastered_topic_ids),
            "weakness_topic_ids": list(self.weakness_topic_ids),
            "review_topic_ids": list(self.review_topic_ids),
            "mastery_target": self.mastery_target,
            "max_session_minutes": self.max_session_minutes,
            "study_minutes_per_week": self.study_minutes_per_week,
            "available_weeks": self.available_weeks,
        }


@dataclass(frozen=True)
class CurriculumValidationIssue:
    code: str
    message: str
    unit_id: Optional[str] = None
    topic_id: Optional[str] = None
    field: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "unit_id": self.unit_id,
            "topic_id": self.topic_id,
            "field": self.field,
        }


@dataclass(frozen=True)
class CurriculumValidationResult:
    valid: bool
    issues: tuple[CurriculumValidationIssue, ...] = field(default_factory=tuple)
    validated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "validated_at": self.validated_at,
        }


@dataclass(frozen=True)
class RegenerationEvidence:
    initial_diagnostic_completed: bool = False
    target_score_changed: bool = False
    previous_target_score: Optional[int] = None
    repeated_failure_topic_id: Optional[str] = None
    repeated_failure_count: int = 0
    mastery_delta: float = 0.0
    materially_updated_topic_count: int = 0
    curriculum_completed: bool = False
    manual_requested: bool = False
    taxonomy_version_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_diagnostic_completed": self.initial_diagnostic_completed,
            "target_score_changed": self.target_score_changed,
            "previous_target_score": self.previous_target_score,
            "repeated_failure_topic_id": self.repeated_failure_topic_id,
            "repeated_failure_count": max(0, int(self.repeated_failure_count)),
            "mastery_delta": round(max(0.0, float(self.mastery_delta)), 4),
            "materially_updated_topic_count": max(0, int(self.materially_updated_topic_count)),
            "curriculum_completed": self.curriculum_completed,
            "manual_requested": self.manual_requested,
            "taxonomy_version_changed": self.taxonomy_version_changed,
        }


@dataclass(frozen=True)
class RegenerationDecision:
    should_regenerate: bool
    trigger: str
    reason: str
    previous_curriculum_id: Optional[str]
    relevant_evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_regenerate": self.should_regenerate,
            "trigger": self.trigger,
            "reason": self.reason,
            "previous_curriculum_id": self.previous_curriculum_id,
            "relevant_evidence": dict(self.relevant_evidence),
        }


def _mastery_target(target_score: int) -> float:
    if target_score <= 150:
        return 0.75
    if target_score < 190:
        return 0.85
    return 0.92


def _allowed_difficulties(target_score: int) -> frozenset[str]:
    if target_score <= 150:
        return frozenset({"foundation"})
    if target_score < 190:
        return frozenset({"foundation", "intermediate"})
    return frozenset({"foundation", "intermediate", "advanced"})


def _starting_level(context: AIContext) -> str:
    explicit_levels = {
        "beginner": "beginner",
        "foundation": "beginner",
        "average": "average",
        "intermediate": "average",
        "strong": "strong",
        "advanced": "strong",
    }
    explicit = explicit_levels.get(context.difficulty.casefold())
    if explicit:
        return explicit
    if context.diagnostic_score is not None and context.diagnostic_total:
        ratio = context.diagnostic_score / context.diagnostic_total
        if ratio < 0.45:
            return "beginner"
        if ratio < 0.75:
            return "average"
        return "strong"
    return "average"


def build_curriculum_policy(
    context: AIContext,
    taxonomy: MathTaxonomy,
    *,
    today: Optional[datetime] = None,
) -> CurriculumPolicy:
    if context.subject != taxonomy.subject:
        raise ValueError("Curriculum context subject does not match the taxonomy")
    target_score = int(context.goal_score or 170)
    if not 100 <= target_score <= 200:
        raise ValueError("Curriculum target score must be between 100 and 200")

    mastery_target = _mastery_target(target_score)
    completed = set(context.completed_topic_ids)
    completed.update(map_legacy_completed_lessons(context.completed_lessons))
    mastered = {
        topic_id
        for topic_id, value in context.mastery_by_topic.items()
        if topic_id in taxonomy.topics_by_id and value >= mastery_target
    }
    mastered.update(topic_id for topic_id in completed if topic_id in taxonomy.topics_by_id)
    weakness_ids = set(resolve_weakness_topic_ids(context.known_weaknesses))
    # Raw answers never enter the prompt.  Known aliases in recent mistakes are
    # reduced locally to canonical topic IDs before curriculum generation.
    weakness_ids.update(resolve_weakness_topic_ids(context.recent_mistakes))
    weakness_ids.update(
        topic_id
        for topic_id, value in context.mastery_by_topic.items()
        if topic_id in taxonomy.topics_by_id and value < 0.5
    )

    allowed_difficulties = _allowed_difficulties(target_score)
    target_topics = {
        topic.id
        for topic in taxonomy.topics
        if topic.difficulty in allowed_difficulties
        and (topic.required or target_score >= 190)
    }
    target_topics.update(weakness_ids)
    target_topics = taxonomy.prerequisite_closure(tuple(target_topics))
    required = {
        topic_id
        for topic_id in target_topics
        if topic_id not in mastered or topic_id in weakness_ids
    }

    allowed = {
        topic.id
        for topic in taxonomy.topics
        if topic.difficulty in allowed_difficulties or topic.id in weakness_ids
    }
    allowed.update(taxonomy.prerequisite_closure(tuple(allowed)))
    ordered_required = tuple(
        topic_id for topic_id in taxonomy.topological_order(tuple(required)) if topic_id in required
    )
    review_topic_ids: tuple[str, ...] = ()
    if not ordered_required:
        target_order = taxonomy.topological_order(tuple(target_topics))
        review_topic_ids = tuple(target_order[-3:])
        ordered_required = review_topic_ids
    ordered_allowed = tuple(
        topic_id for topic_id in taxonomy.topological_order(tuple(allowed)) if topic_id in allowed
    )

    weekly_minutes = int(context.study_minutes_per_week or 240)
    max_session_minutes = 45 if weekly_minutes < 180 else 60
    now = today or datetime.now(timezone.utc)
    available_weeks = None
    if context.desired_exam_date:
        exam_date = datetime.fromisoformat(context.desired_exam_date).date()
        available_weeks = max(0, math.ceil((exam_date - now.date()).days / 7))

    return CurriculumPolicy(
        target_score=target_score,
        starting_level=_starting_level(context),
        required_topic_ids=ordered_required,
        allowed_topic_ids=ordered_allowed,
        mastered_topic_ids=tuple(sorted(mastered)),
        weakness_topic_ids=tuple(sorted(weakness_ids)),
        review_topic_ids=review_topic_ids,
        mastery_target=mastery_target,
        max_session_minutes=max_session_minutes,
        study_minutes_per_week=weekly_minutes,
        available_weeks=available_weeks,
    )


def curriculum_context_fingerprint(context: AIContext, taxonomy: MathTaxonomy) -> str:
    return build_cache_key(
        "curriculum-context-v1",
        context.user_id,
        context.subject,
        context.goal_score,
        context.difficulty,
        tuple(context.completed_lessons),
        tuple(context.completed_topic_ids),
        dict(context.mastery_by_topic),
        tuple(context.known_weaknesses),
        resolve_weakness_topic_ids(context.recent_mistakes),
        context.diagnostic_score,
        context.diagnostic_total,
        context.study_minutes_per_week,
        context.desired_exam_date,
        context.active_curriculum_id,
        taxonomy.version,
    )


def curriculum_request_fingerprint(
    *,
    context_fingerprint: str,
    taxonomy_version: str,
    prompt_version: str,
    schema_version: str,
    model_identifier: str,
    generation_reason: str,
) -> str:
    return build_cache_key(
        "curriculum-request-v1",
        context_fingerprint,
        taxonomy_version,
        prompt_version,
        schema_version,
        model_identifier,
        generation_reason,
    )


def curriculum_policy_from_curriculum(curriculum: Curriculum) -> CurriculumPolicy:
    """Rebuild the immutable policy recorded with a persisted curriculum."""

    metadata = curriculum.generation_metadata
    return CurriculumPolicy(
        target_score=curriculum.target_score,
        starting_level=curriculum.starting_level,
        required_topic_ids=metadata.required_topic_ids,
        allowed_topic_ids=metadata.allowed_topic_ids,
        mastered_topic_ids=metadata.mastered_topic_ids,
        weakness_topic_ids=metadata.weakness_topic_ids,
        review_topic_ids=metadata.review_topic_ids,
        mastery_target=_mastery_target(curriculum.target_score),
        max_session_minutes=metadata.max_session_minutes,
        study_minutes_per_week=metadata.study_minutes_per_week,
        available_weeks=metadata.available_weeks,
    )


def validate_curriculum(
    curriculum: Curriculum,
    taxonomy: MathTaxonomy,
    *,
    policy: Optional[CurriculumPolicy] = None,
) -> CurriculumValidationResult:
    policy = policy or curriculum_policy_from_curriculum(curriculum)
    issues: list[CurriculumValidationIssue] = []
    if curriculum.subject != taxonomy.subject:
        issues.append(CurriculumValidationIssue(
            "subject_mismatch", "Curriculum subject does not match taxonomy", field="subject"
        ))
    if curriculum.taxonomy_version != taxonomy.version:
        issues.append(CurriculumValidationIssue(
            "taxonomy_version_mismatch",
            "Curriculum taxonomy version is not current",
            field="taxonomy_version",
        ))
    if not curriculum.units:
        issues.append(CurriculumValidationIssue("empty_curriculum", "Curriculum has no units"))
        return CurriculumValidationResult(False, tuple(issues))

    topic_positions = {unit.topic_id: unit.order for unit in curriculum.units}
    selected_ids = set(topic_positions)
    unknown = selected_ids - set(taxonomy.topics_by_id)
    for topic_id in sorted(unknown):
        issues.append(CurriculumValidationIssue(
            "unknown_topic", f"Unknown curriculum topic: {topic_id}", topic_id=topic_id
        ))
    missing_required = set(policy.required_topic_ids) - selected_ids
    for topic_id in sorted(missing_required):
        issues.append(CurriculumValidationIssue(
            "missing_required_topic",
            f"Required topic is missing: {topic_id}",
            topic_id=topic_id,
        ))
    disallowed = selected_ids - set(policy.allowed_topic_ids)
    for topic_id in sorted(disallowed):
        issues.append(CurriculumValidationIssue(
            "topic_incompatible_with_target",
            f"Topic is not allowed by the target-score policy: {topic_id}",
            topic_id=topic_id,
        ))

    mastered = set(policy.mastered_topic_ids)
    weaknesses = set(policy.weakness_topic_ids)
    scheduled_reviews = set(policy.review_topic_ids)
    total_minutes = 0
    for unit in curriculum.units:
        if unit.topic_id not in taxonomy.topics_by_id:
            continue
        topic = taxonomy.topic(unit.topic_id)
        total_minutes += unit.estimated_duration_minutes
        if unit.priority not in ALLOWED_PRIORITIES:
            issues.append(CurriculumValidationIssue(
                "invalid_priority", f"Invalid unit priority: {unit.priority}", unit.id,
                unit.topic_id, "priority",
            ))
        if unit.reason_code not in ALLOWED_UNIT_REASONS:
            issues.append(CurriculumValidationIssue(
                "invalid_reason", f"Invalid unit reason: {unit.reason_code}", unit.id,
                unit.topic_id, "reason_code",
            ))
        if unit.difficulty != topic.difficulty:
            issues.append(CurriculumValidationIssue(
                "difficulty_mismatch", "Unit difficulty does not match taxonomy", unit.id,
                unit.topic_id, "difficulty",
            ))
        minimum_duration = max(15, math.floor(topic.estimated_minutes * 0.5))
        maximum_duration = min(600, math.ceil(topic.estimated_minutes * 1.5))
        if not minimum_duration <= unit.estimated_duration_minutes <= maximum_duration:
            issues.append(CurriculumValidationIssue(
                "impossible_duration", "Unit duration is outside the safe taxonomy range", unit.id,
                unit.topic_id, "estimated_duration_minutes",
            ))
        per_session = math.ceil(unit.estimated_duration_minutes / unit.study_sessions)
        if per_session > policy.max_session_minutes:
            issues.append(CurriculumValidationIssue(
                "unrealistic_session", "Unit creates an unrealistic study session", unit.id,
                unit.topic_id, "study_sessions",
            ))
        if unit.mastery_target < max(0.65, policy.mastery_target - 0.05) or unit.mastery_target > 0.98:
            issues.append(CurriculumValidationIssue(
                "invalid_mastery_target", "Unit mastery target is incompatible with the score goal",
                unit.id, unit.topic_id, "mastery_target",
            ))
        if tuple(unit.prerequisite_topic_ids) != tuple(topic.prerequisite_topic_ids):
            issues.append(CurriculumValidationIssue(
                "prerequisite_mismatch", "Unit prerequisites do not match taxonomy", unit.id,
                unit.topic_id, "prerequisite_topic_ids",
            ))
        if topic.prerequisite_topic_ids and not unit.prerequisite_explanation.strip():
            issues.append(CurriculumValidationIssue(
                "missing_prerequisite_explanation", "Prerequisite explanation is required", unit.id,
                unit.topic_id, "prerequisite_explanation",
            ))
        if len(unit.prerequisite_explanation) > 400:
            issues.append(CurriculumValidationIssue(
                "prerequisite_explanation_too_long", "Prerequisite explanation is too long", unit.id,
                unit.topic_id, "prerequisite_explanation",
            ))
        for prerequisite_id in topic.prerequisite_topic_ids:
            if prerequisite_id in mastered:
                continue
            if prerequisite_id not in topic_positions:
                issues.append(CurriculumValidationIssue(
                    "unmet_prerequisite", f"Missing prerequisite: {prerequisite_id}", unit.id,
                    unit.topic_id, "prerequisite_topic_ids",
                ))
            elif topic_positions[prerequisite_id] >= unit.order:
                issues.append(CurriculumValidationIssue(
                    "invalid_prerequisite_order", f"Prerequisite appears too late: {prerequisite_id}",
                    unit.id, unit.topic_id, "order",
                ))
        for recommended_id in topic.recommended_after_topic_ids:
            if recommended_id in topic_positions and topic_positions[recommended_id] >= unit.order:
                issues.append(CurriculumValidationIssue(
                    "invalid_recommended_order", f"Recommended predecessor appears too late: {recommended_id}",
                    unit.id, unit.topic_id, "order",
                ))
        if unit.topic_id in mastered and unit.topic_id not in weaknesses | scheduled_reviews:
            issues.append(CurriculumValidationIssue(
                "unjustified_mastered_topic", "Mastered topic was included without a review need",
                unit.id, unit.topic_id, "reason_code",
            ))
        if unit.topic_id in mastered and unit.reason_code != "review_mastered":
            issues.append(CurriculumValidationIssue(
                "invalid_mastered_topic_reason", "A mastered topic must be marked as review_mastered",
                unit.id, unit.topic_id, "reason_code",
            ))

    checkpoint_ids: set[str] = set()
    for checkpoint in curriculum.review_checkpoints:
        total_minutes += checkpoint.estimated_minutes
        if checkpoint.id in checkpoint_ids:
            issues.append(CurriculumValidationIssue(
                "duplicate_checkpoint", f"Duplicate checkpoint ID: {checkpoint.id}"
            ))
        checkpoint_ids.add(checkpoint.id)
        if not 1 <= checkpoint.after_unit_order <= len(curriculum.units):
            issues.append(CurriculumValidationIssue(
                "invalid_checkpoint_position", "Review checkpoint position is invalid"
            ))
        if checkpoint.reason_code not in ALLOWED_CHECKPOINT_REASONS:
            issues.append(CurriculumValidationIssue(
                "invalid_checkpoint_reason", "Review checkpoint reason is invalid"
            ))
        if not 15 <= checkpoint.estimated_minutes <= 120:
            issues.append(CurriculumValidationIssue(
                "invalid_checkpoint_duration", "Review checkpoint duration is invalid"
            ))
        for topic_id in checkpoint.topic_ids:
            if topic_id not in topic_positions:
                issues.append(CurriculumValidationIssue(
                    "unknown_checkpoint_topic", f"Checkpoint topic is not in curriculum: {topic_id}",
                    topic_id=topic_id,
                ))
            elif topic_positions[topic_id] > checkpoint.after_unit_order:
                issues.append(CurriculumValidationIssue(
                    "checkpoint_topic_not_studied", f"Checkpoint reviews a future topic: {topic_id}",
                    topic_id=topic_id,
                ))
    if len(curriculum.units) >= 4:
        positions = sorted(checkpoint.after_unit_order for checkpoint in curriculum.review_checkpoints)
        if not positions or positions[-1] != len(curriculum.units):
            issues.append(CurriculumValidationIssue(
                "missing_final_checkpoint", "Curriculum needs a final review checkpoint"
            ))
        previous = 0
        for position in positions:
            if position - previous > 6:
                issues.append(CurriculumValidationIssue(
                    "review_gap_too_large", "More than six units occur without a review checkpoint"
                ))
            previous = position

    if policy.available_weeks is not None:
        capacity = policy.available_weeks * policy.study_minutes_per_week
        if policy.available_weeks <= 0 or total_minutes > capacity:
            issues.append(CurriculumValidationIssue(
                "unrealistic_workload",
                "Curriculum cannot fit the available study time before the exam",
                field="estimated_duration_minutes",
            ))
    return CurriculumValidationResult(not issues, tuple(issues))


def should_regenerate_curriculum(
    active_curriculum: Optional[Curriculum],
    taxonomy: MathTaxonomy,
    evidence: RegenerationEvidence,
    *,
    now: Optional[datetime] = None,
    cooldown_hours: int = 24,
) -> RegenerationDecision:
    now = now or datetime.now(timezone.utc)
    previous_id = active_curriculum.id if active_curriculum else None
    evidence_dict = evidence.to_dict()

    if evidence.manual_requested:
        return RegenerationDecision(True, "manual_request", "Manual regeneration was requested", previous_id, evidence_dict)
    if evidence.taxonomy_version_changed or (
        active_curriculum and active_curriculum.taxonomy_version != taxonomy.version
    ):
        return RegenerationDecision(True, "taxonomy_updated", "The canonical taxonomy version changed", previous_id, evidence_dict)
    if active_curriculum is None:
        if evidence.initial_diagnostic_completed:
            return RegenerationDecision(True, "initial_diagnostic", "Initial diagnostic data is available", None, evidence_dict)
        return RegenerationDecision(False, "awaiting_diagnostic", "No active curriculum and no completed diagnostic", None, evidence_dict)
    if evidence.target_score_changed:
        return RegenerationDecision(True, "target_score_changed", "The learner target score changed", previous_id, evidence_dict)

    trigger = None
    reason = None
    if evidence.repeated_failure_count >= 3 and evidence.repeated_failure_topic_id:
        trigger = "repeated_prerequisite_failure"
        reason = "A prerequisite topic has at least three recent failures"
    elif evidence.mastery_delta >= 0.2 or evidence.materially_updated_topic_count >= 3:
        trigger = "major_mastery_update"
        reason = "Mastery changed materially across the roadmap"
    elif evidence.curriculum_completed:
        trigger = "curriculum_completed"
        reason = "The active curriculum is complete"
    if trigger is None:
        return RegenerationDecision(False, "no_material_change", "No regeneration threshold was met", previous_id, evidence_dict)

    created_at = datetime.fromisoformat(active_curriculum.created_at.replace("Z", "+00:00"))
    if now - created_at < timedelta(hours=max(1, cooldown_hours)):
        return RegenerationDecision(False, "cooldown", "Automatic regeneration is inside the cooldown window", previous_id, {
            **evidence_dict,
            "candidate_trigger": trigger,
            "cooldown_hours": cooldown_hours,
        })
    return RegenerationDecision(True, trigger, reason or trigger, previous_id, evidence_dict)
