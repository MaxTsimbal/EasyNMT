"""Lesson engine: expands one curriculum plan into a complete lesson."""
from __future__ import annotations

from ..cache import build_cache_key
from ..errors import EngineResult
from ..models import AIModelValidationError, LearningPlan, Lesson
from ..prompts.lesson import build_lesson_prompt
from ..schemas import AIContext
from .base import AIEngine


class LessonEngine(AIEngine[Lesson]):
    """Generate lesson content without changing unlock or completion state."""

    name = "lesson"
    cache_namespace = "lesson"

    def generate(
        self,
        context: AIContext,
        plan: LearningPlan,
        *,
        force_refresh: bool = False,
    ) -> EngineResult[Lesson]:
        prompt = build_lesson_prompt(context, plan)
        cache_key = build_cache_key("v1", context.for_prompt(), plan.to_dict())

        def parse(payload):
            lesson = Lesson.from_dict(payload)
            if lesson.id != plan.id:
                raise AIModelValidationError("lesson ID does not match the learning plan")
            if lesson.subject != context.subject:
                raise AIModelValidationError("lesson subject does not match the request")
            return lesson

        return self.orchestrator.execute_structured(
            engine_name=self.name,
            context=context,
            prompt=prompt,
            parser=parse,
            cache_namespace=self.cache_namespace,
            cache_key=cache_key,
            cache_ttl_seconds=self.cache_ttl_seconds,
            force_refresh=force_refresh,
        )
