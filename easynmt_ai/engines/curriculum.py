"""Curriculum engine: creates and later updates learner roadmaps."""
from __future__ import annotations

from ..cache import build_cache_key
from ..errors import EngineResult
from ..models import AIModelValidationError, Curriculum
from ..prompts.curriculum import build_curriculum_prompt
from ..schemas import AIContext
from .base import AIEngine


class CurriculumEngine(AIEngine[Curriculum]):
    """Generate a sequenced roadmap from a learner snapshot.

    The engine never unlocks lessons or writes progress; the Flask/SQLite layer
    remains authoritative for those decisions.
    """

    name = "curriculum"
    cache_namespace = "curriculum"

    def generate(
        self,
        context: AIContext,
        *,
        lesson_count: int = 12,
        force_refresh: bool = False,
    ) -> EngineResult[Curriculum]:
        if not 1 <= lesson_count <= 100:
            raise ValueError("lesson_count must be between 1 and 100")
        prompt = build_curriculum_prompt(context, lesson_count=lesson_count)
        cache_key = build_cache_key("v1", context.for_prompt(), lesson_count)

        def parse(payload):
            curriculum = Curriculum.from_dict(payload)
            if curriculum.subject != context.subject:
                raise AIModelValidationError("curriculum subject does not match the request")
            if len(curriculum.plans) != lesson_count:
                raise AIModelValidationError("curriculum lesson count does not match the request")
            if context.goal_score is not None and curriculum.goal_score != context.goal_score:
                raise AIModelValidationError("curriculum goal score does not match the request")
            return curriculum

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
