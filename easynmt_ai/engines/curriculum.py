"""Production curriculum engine constrained by EasyNMT's mathematics taxonomy."""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from ..curriculum.policy import (
    GENERATION_REASONS,
    CurriculumPolicy,
    build_curriculum_policy,
    curriculum_context_fingerprint,
    curriculum_policy_from_curriculum,
    curriculum_request_fingerprint,
    validate_curriculum,
)
from ..curriculum.taxonomy import MathTaxonomy, load_math_taxonomy
from ..errors import AIError, AIErrorCode, EngineResult
from ..models import (
    AIModelValidationError,
    Curriculum,
    CurriculumGenerationMetadata,
    CurriculumStatus,
    CurriculumUnit,
    ReviewCheckpoint,
)
from ..prompts.curriculum import (
    CURRICULUM_PROMPT_VERSION,
    CURRICULUM_SCHEMA_VERSION,
    build_curriculum_prompt,
)
from ..schemas import AIContext
from .base import AIEngine


class CurriculumEngine(AIEngine[Curriculum]):
    """Generate validated mathematics roadmap drafts.

    OpenAI chooses pacing and priority only within a deterministic candidate
    set. Topic definitions, prerequisites, lifecycle state, IDs, and metadata
    always come from EasyNMT.
    """

    name = "curriculum"
    cache_namespace = "curriculum"
    cache_ttl_seconds = 6 * 60 * 60

    def __init__(
        self,
        orchestrator,
        *,
        taxonomy: Optional[MathTaxonomy] = None,
        max_output_tokens: int = 5000,
    ) -> None:
        super().__init__(orchestrator)
        self.taxonomy = taxonomy or load_math_taxonomy()
        self.max_output_tokens = max(1000, int(max_output_tokens))

    @property
    def model_identifier(self) -> str:
        return self.orchestrator.model_identifier

    def generation_identity(
        self,
        context: AIContext,
        *,
        generation_reason: str,
    ) -> tuple[str, str, CurriculumPolicy]:
        if generation_reason not in GENERATION_REASONS:
            raise ValueError(f"Unsupported curriculum generation reason: {generation_reason}")
        policy = build_curriculum_policy(context, self.taxonomy)
        context_fingerprint = curriculum_context_fingerprint(context, self.taxonomy)
        request_fingerprint = curriculum_request_fingerprint(
            context_fingerprint=context_fingerprint,
            taxonomy_version=self.taxonomy.version,
            prompt_version=CURRICULUM_PROMPT_VERSION,
            schema_version=CURRICULUM_SCHEMA_VERSION,
            model_identifier=self.model_identifier,
            generation_reason=generation_reason,
        )
        return context_fingerprint, request_fingerprint, policy

    @staticmethod
    def _usage_value(usage: Optional[Mapping[str, Any]], name: str) -> Optional[int]:
        if not usage or usage.get(name) is None:
            return None
        try:
            return int(usage[name])
        except (TypeError, ValueError):
            return None

    def _metadata(
        self,
        *,
        source: str,
        context_fingerprint: str,
        request_fingerprint: str,
        policy: CurriculumPolicy,
        response_id: Optional[str] = None,
        usage: Optional[Mapping[str, Any]] = None,
        fallback_error_code: Optional[str] = None,
    ) -> CurriculumGenerationMetadata:
        return CurriculumGenerationMetadata(
            source=source,
            context_fingerprint=context_fingerprint,
            request_fingerprint=request_fingerprint,
            required_topic_ids=policy.required_topic_ids,
            allowed_topic_ids=policy.allowed_topic_ids,
            mastered_topic_ids=policy.mastered_topic_ids,
            weakness_topic_ids=policy.weakness_topic_ids,
            review_topic_ids=policy.review_topic_ids,
            max_session_minutes=policy.max_session_minutes,
            study_minutes_per_week=policy.study_minutes_per_week,
            available_weeks=policy.available_weeks,
            provider_response_id=response_id,
            input_tokens=self._usage_value(usage, "input_tokens"),
            output_tokens=self._usage_value(usage, "output_tokens"),
            total_tokens=self._usage_value(usage, "total_tokens"),
            fallback_error_code=fallback_error_code,
        )

    def _curriculum_from_proposal(
        self,
        payload: Mapping[str, Any],
        *,
        context: AIContext,
        policy: CurriculumPolicy,
        generation_reason: str,
        curriculum_version: int,
        context_fingerprint: str,
        request_fingerprint: str,
        created_at: str,
        source: str = "openai",
        fallback_error_code: Optional[str] = None,
    ) -> Curriculum:
        # Cached entries contain the complete trusted model. Provider proposals
        # contain only units and checkpoints and are wrapped locally below.
        if "id" in payload and "generation_metadata" in payload:
            curriculum = Curriculum.from_dict(payload)
            validation = validate_curriculum(curriculum, self.taxonomy, policy=policy)
            if not validation.valid:
                raise AIModelValidationError(
                    "Cached curriculum failed validation: "
                    + ", ".join(issue.code for issue in validation.issues[:5])
                )
            return curriculum

        raw_units = payload.get("units")
        if not isinstance(raw_units, Sequence) or isinstance(raw_units, (str, bytes)):
            raise AIModelValidationError("curriculum proposal units must be an array")
        units: list[CurriculumUnit] = []
        seen_topics: set[str] = set()
        for order, raw_unit in enumerate(raw_units, 1):
            if not isinstance(raw_unit, Mapping):
                raise AIModelValidationError("curriculum proposal unit must be an object")
            topic_id = str(raw_unit.get("topic_id") or "").strip()
            if topic_id not in self.taxonomy.topics_by_id:
                raise AIModelValidationError(f"unknown curriculum topic: {topic_id}")
            if topic_id in seen_topics:
                raise AIModelValidationError(f"duplicate curriculum topic: {topic_id}")
            seen_topics.add(topic_id)
            topic = self.taxonomy.topic(topic_id)
            prerequisite_titles = [
                self.taxonomy.topic(item).title_uk
                for item in topic.prerequisite_topic_ids
            ]
            prerequisite_explanation = (
                "Спочатку потрібні теми: " + ", ".join(prerequisite_titles) + "."
                if prerequisite_titles
                else ""
            )
            units.append(CurriculumUnit(
                id=f"unit-{order:03d}-{topic.slug}",
                order=order,
                topic_id=topic.id,
                prerequisite_topic_ids=topic.prerequisite_topic_ids,
                prerequisite_explanation=prerequisite_explanation,
                priority=str(raw_unit.get("priority") or ""),
                difficulty=topic.difficulty,
                estimated_duration_minutes=int(raw_unit.get("estimated_duration_minutes") or 0),
                study_sessions=int(raw_unit.get("study_sessions") or 0),
                mastery_target=float(raw_unit.get("mastery_target") or 0),
                reason_code=str(raw_unit.get("reason_code") or ""),
            ))

        raw_checkpoints = payload.get("review_checkpoints", ())
        if not isinstance(raw_checkpoints, Sequence) or isinstance(raw_checkpoints, (str, bytes)):
            raise AIModelValidationError("review checkpoints must be an array")
        checkpoints: list[ReviewCheckpoint] = []
        for index, raw_checkpoint in enumerate(raw_checkpoints, 1):
            if not isinstance(raw_checkpoint, Mapping):
                raise AIModelValidationError("review checkpoint must be an object")
            raw_topic_ids = raw_checkpoint.get("topic_ids", ())
            if not isinstance(raw_topic_ids, Sequence) or isinstance(raw_topic_ids, (str, bytes)):
                raise AIModelValidationError("review checkpoint topic IDs must be an array")
            checkpoints.append(ReviewCheckpoint(
                id=f"checkpoint-{index:03d}",
                after_unit_order=int(raw_checkpoint.get("after_unit_order") or 0),
                topic_ids=tuple(str(item) for item in raw_topic_ids),
                reason_code=str(raw_checkpoint.get("reason_code") or ""),
                estimated_minutes=int(raw_checkpoint.get("estimated_minutes") or 0),
            ))

        curriculum = Curriculum(
            id=f"cur-{request_fingerprint[:24]}",
            curriculum_version=max(1, int(curriculum_version)),
            taxonomy_version=self.taxonomy.version,
            user_id=context.user_id,
            subject=self.taxonomy.subject,
            target_score=policy.target_score,
            starting_level=policy.starting_level,
            status=CurriculumStatus.DRAFT,
            creation_reason=generation_reason,
            units=tuple(units),
            review_checkpoints=tuple(checkpoints),
            generation_metadata=self._metadata(
                source=source,
                context_fingerprint=context_fingerprint,
                request_fingerprint=request_fingerprint,
                policy=policy,
                fallback_error_code=fallback_error_code,
            ),
            prompt_version=CURRICULUM_PROMPT_VERSION,
            schema_version=CURRICULUM_SCHEMA_VERSION,
            model_identifier=self.model_identifier,
            created_at=created_at,
        )
        # Re-parse once through the shared model to validate primitive types.
        curriculum = Curriculum.from_dict(curriculum.to_dict())
        validation = validate_curriculum(curriculum, self.taxonomy, policy=policy)
        if not validation.valid:
            raise AIModelValidationError(
                "Curriculum proposal failed validation: "
                + ", ".join(issue.code for issue in validation.issues[:8])
            )
        return curriculum

    def _deterministic_payload(self, policy: CurriculumPolicy) -> dict[str, Any]:
        units = []
        weaknesses = set(policy.weakness_topic_ids)
        mastered = set(policy.mastered_topic_ids)
        scheduled_reviews = set(policy.review_topic_ids)
        for topic_id in policy.required_topic_ids:
            topic = self.taxonomy.topic(topic_id)
            if topic_id in mastered and topic_id in weaknesses | scheduled_reviews:
                reason = "review_mastered"
                priority = "critical"
            elif topic_id in weaknesses:
                reason = "known_weakness"
                priority = "critical"
            elif topic.difficulty == "advanced":
                reason = "advanced_target"
                priority = "high"
            elif topic.required:
                reason = "core_for_target"
                priority = "high" if policy.starting_level == "beginner" else "normal"
            else:
                reason = "unmet_prerequisite"
                priority = "high"
            duration = topic.estimated_minutes
            units.append({
                "topic_id": topic_id,
                "priority": priority,
                "estimated_duration_minutes": duration,
                "study_sessions": max(1, math.ceil(duration / policy.max_session_minutes)),
                "mastery_target": policy.mastery_target,
                "reason_code": reason,
            })

        checkpoints = []
        for end in range(4, len(units) + 1, 4):
            start = max(0, end - 4)
            checkpoints.append({
                "after_unit_order": end,
                "topic_ids": [item["topic_id"] for item in units[start:end]],
                "reason_code": "periodic_review",
                "estimated_minutes": min(120, max(30, 15 * (end - start))),
            })
        if units and (not checkpoints or checkpoints[-1]["after_unit_order"] != len(units)):
            start = checkpoints[-1]["after_unit_order"] if checkpoints else 0
            checkpoints.append({
                "after_unit_order": len(units),
                "topic_ids": [item["topic_id"] for item in units[start:]],
                "reason_code": "final_review",
                "estimated_minutes": min(120, max(30, 15 * (len(units) - start))),
            })
        elif checkpoints:
            checkpoints[-1]["reason_code"] = "final_review"
        return {"units": units, "review_checkpoints": checkpoints}

    def deterministic_baseline(
        self,
        context: AIContext,
        *,
        generation_reason: str = "manual_request",
        existing_curriculum: Curriculum | None = None,
    ) -> Curriculum:
        """Build a locally validated baseline without contacting a provider.

        The baseline uses the same taxonomy, policy, identifiers, models, and
        validator as provider-backed generation. An existing deterministic
        curriculum can be supplied to reconstruct only its expected immutable
        structure for safe missing-row repair.
        """

        if existing_curriculum is None:
            context_fingerprint, request_fingerprint, policy = self.generation_identity(
                context,
                generation_reason=generation_reason,
            )
            curriculum_version = 1
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        else:
            if existing_curriculum.user_id != context.user_id:
                raise ValueError("existing curriculum owner does not match context")
            if existing_curriculum.subject != context.subject:
                raise ValueError("existing curriculum subject does not match context")
            policy = curriculum_policy_from_curriculum(existing_curriculum)
            context_fingerprint = (
                existing_curriculum.generation_metadata.context_fingerprint
            )
            request_fingerprint = (
                existing_curriculum.generation_metadata.request_fingerprint
            )
            generation_reason = existing_curriculum.creation_reason
            curriculum_version = existing_curriculum.curriculum_version
            created_at = existing_curriculum.created_at

        baseline = self._curriculum_from_proposal(
            self._deterministic_payload(policy),
            context=context,
            policy=policy,
            generation_reason=generation_reason,
            curriculum_version=curriculum_version,
            context_fingerprint=context_fingerprint,
            request_fingerprint=request_fingerprint,
            created_at=created_at,
            source="deterministic",
        )
        if existing_curriculum is None:
            return baseline
        return replace(
            baseline,
            id=existing_curriculum.id,
            curriculum_version=existing_curriculum.curriculum_version,
            status=existing_curriculum.status,
            creation_reason=existing_curriculum.creation_reason,
            generation_metadata=existing_curriculum.generation_metadata,
            prompt_version=existing_curriculum.prompt_version,
            schema_version=existing_curriculum.schema_version,
            model_identifier=existing_curriculum.model_identifier,
            created_at=existing_curriculum.created_at,
        )

    def generate(
        self,
        context: AIContext,
        *,
        generation_reason: str = "manual_request",
        active_curriculum: Optional[Curriculum] = None,
        curriculum_version: int = 1,
        allow_fallback: bool = True,
        force_refresh: bool = False,
    ) -> EngineResult[Curriculum]:
        context_fingerprint, request_fingerprint, policy = self.generation_identity(
            context,
            generation_reason=generation_reason,
        )
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        prompt = build_curriculum_prompt(
            context,
            taxonomy=self.taxonomy,
            policy=policy,
            generation_reason=generation_reason,
            active_curriculum=active_curriculum,
        )

        def parse(payload: Mapping[str, Any]) -> Curriculum:
            return self._curriculum_from_proposal(
                payload,
                context=context,
                policy=policy,
                generation_reason=generation_reason,
                curriculum_version=curriculum_version,
                context_fingerprint=context_fingerprint,
                request_fingerprint=request_fingerprint,
                created_at=created_at,
            )

        result = self.orchestrator.execute_structured(
            engine_name=self.name,
            context=context,
            prompt=prompt,
            parser=parse,
            cache_namespace=self.cache_namespace,
            cache_key=request_fingerprint,
            cache_ttl_seconds=self.cache_ttl_seconds,
            force_refresh=force_refresh,
            max_output_tokens=(
                min(self.max_output_tokens, context.available_tokens)
                if context.available_tokens is not None
                else self.max_output_tokens
            ),
        )
        if result.success:
            curriculum = result.value
            enriched_metadata = replace(
                curriculum.generation_metadata,
                provider_response_id=result.response_id,
                input_tokens=self._usage_value(result.usage, "input_tokens"),
                output_tokens=self._usage_value(result.usage, "output_tokens"),
                total_tokens=self._usage_value(result.usage, "total_tokens"),
            )
            return replace(result, value=replace(curriculum, generation_metadata=enriched_metadata))
        if not allow_fallback:
            return result

        provider_error = result.error or AIError(
            AIErrorCode.INTERNAL_ERROR,
            "Curriculum generation failed.",
        )
        try:
            fallback = self._curriculum_from_proposal(
                self._deterministic_payload(policy),
                context=context,
                policy=policy,
                generation_reason=generation_reason,
                curriculum_version=curriculum_version,
                context_fingerprint=context_fingerprint,
                request_fingerprint=request_fingerprint,
                created_at=created_at,
                source="deterministic",
                fallback_error_code=provider_error.code.value,
            )
        except (AIModelValidationError, TypeError, ValueError) as exc:
            fallback_error = AIError(
                AIErrorCode.VALIDATION_ERROR,
                "A safe baseline curriculum could not satisfy local validation.",
                retryable=False,
                details={"reason": str(exc)[:200]},
            )
            return EngineResult(
                error=fallback_error,
                usage=result.usage,
                response_id=result.response_id,
                warnings=(provider_error,),
            )
        return EngineResult(
            value=fallback,
            usage=result.usage,
            response_id=result.response_id,
            warnings=(provider_error,),
            fallback_used=True,
        )
