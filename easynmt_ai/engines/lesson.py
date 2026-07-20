"""Production Lesson Engine for complete, validated curriculum-unit lessons."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

from ..cache import build_cache_key
from ..errors import EngineResult
from ..lessons import (
    Lesson,
    LessonGenerationMetadata,
    LessonGenerationRequest,
    validate_lesson,
)
from ..models import AIModelValidationError, LearningPlan
from ..prompts.lesson import (
    LESSON_PROMPT_VERSION,
    LESSON_SCHEMA_VERSION,
    build_lesson_prompt,
    lesson_prompt_context,
)
from ..schemas import AIContext
from .base import AIEngine


class LessonEngine(AIEngine[Lesson]):
    """Generate complete teaching content without mutating learner progress."""

    name = "lesson"
    cache_namespace = "lesson"
    cache_ttl_seconds = 7 * 24 * 60 * 60

    def __init__(self, orchestrator, *, max_output_tokens: int = 6500) -> None:
        super().__init__(orchestrator)
        self.max_output_tokens = max(2500, int(max_output_tokens))

    @property
    def model_identifier(self) -> str:
        return self.orchestrator.model_identifier

    def generation_identity(
        self,
        context: AIContext,
        request: LessonGenerationRequest,
    ) -> str:
        return build_cache_key(
            LESSON_PROMPT_VERSION,
            LESSON_SCHEMA_VERSION,
            self.model_identifier,
            {
                "curriculum_id": request.curriculum_id,
                "curriculum_unit_id": request.curriculum_unit_id,
                **request.for_prompt(),
            },
            lesson_prompt_context(context, request),
        )

    @staticmethod
    def _usage_value(usage: Mapping[str, Any] | None, name: str) -> int | None:
        if not usage or usage.get(name) is None:
            return None
        try:
            return int(usage[name])
        except (TypeError, ValueError):
            return None

    def _lesson_from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        request: LessonGenerationRequest,
        request_fingerprint: str,
        generated_at: str,
    ) -> Lesson:
        if "generation_metadata" in payload:
            lesson = Lesson.from_dict(payload)
        else:
            complete = dict(payload)
            complete.update({
                "id": request.lesson_id,
                "curriculum_id": request.curriculum_id,
                "curriculum_unit_id": request.curriculum_unit_id,
                "topic_id": request.topic_id,
                "title": request.title,
                "subject": request.subject,
                "difficulty": request.difficulty,
                "estimated_minutes": request.estimated_minutes,
                "objectives": list(request.objectives),
                "competencies": list(request.competencies),
                "generation_metadata": LessonGenerationMetadata(
                    source="openai",
                    request_fingerprint=request_fingerprint,
                    prompt_version=LESSON_PROMPT_VERSION,
                    schema_version=LESSON_SCHEMA_VERSION,
                    model_identifier=self.model_identifier,
                    generated_at=generated_at,
                ).to_dict(),
            })
            lesson = Lesson.from_dict(complete)
        if lesson.generation_metadata.request_fingerprint != request_fingerprint:
            raise AIModelValidationError("lesson request fingerprint does not match")
        validation = validate_lesson(lesson, request)
        if not validation.valid:
            codes = ", ".join(issue.code for issue in validation.issues[:8])
            raise AIModelValidationError(f"lesson failed production validation: {codes}")
        return lesson

    def generate(
        self,
        context: AIContext,
        plan: LessonGenerationRequest | LearningPlan,
        *,
        force_refresh: bool = False,
    ) -> EngineResult[Lesson]:
        request = (
            plan
            if isinstance(plan, LessonGenerationRequest)
            else LessonGenerationRequest.from_learning_plan(context, plan)
        )
        if context.subject != request.subject:
            raise ValueError("lesson subject does not match the learner context")
        request_fingerprint = self.generation_identity(context, request)
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        prompt = build_lesson_prompt(context, request)

        def parse(payload: Mapping[str, Any]) -> Lesson:
            return self._lesson_from_payload(
                payload,
                request=request,
                request_fingerprint=request_fingerprint,
                generated_at=generated_at,
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
        if not result.success:
            return result
        metadata = replace(
            result.value.generation_metadata,
            provider_response_id=result.response_id,
            input_tokens=self._usage_value(result.usage, "input_tokens"),
            output_tokens=self._usage_value(result.usage, "output_tokens"),
            total_tokens=self._usage_value(result.usage, "total_tokens"),
        )
        return replace(result, value=replace(result.value, generation_metadata=metadata))
