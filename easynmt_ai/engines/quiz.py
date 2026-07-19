"""Quiz engine: generates assessments tied to a complete lesson."""
from __future__ import annotations

from ..cache import build_cache_key
from ..errors import EngineResult
from ..models import AIModelValidationError, Lesson, Quiz
from ..prompts.quiz import build_quiz_prompt
from ..schemas import AIContext
from .base import AIEngine


class QuizEngine(AIEngine[Quiz]):
    """Generate a quiz and answer key without recording an attempt."""

    name = "quiz"
    cache_namespace = "quiz"

    def generate(
        self,
        context: AIContext,
        lesson: Lesson,
        *,
        question_count: int = 12,
        force_refresh: bool = False,
    ) -> EngineResult[Quiz]:
        if not 1 <= question_count <= 50:
            raise ValueError("question_count must be between 1 and 50")
        prompt = build_quiz_prompt(context, lesson, question_count=question_count)
        cache_key = build_cache_key("v1", context.for_prompt(), lesson.to_dict(), question_count)

        def parse(payload):
            quiz = Quiz.from_dict(payload)
            if quiz.lesson_id != lesson.id:
                raise AIModelValidationError("quiz lesson ID does not match the request")
            if len(quiz.questions) != question_count:
                raise AIModelValidationError("quiz question count does not match the request")
            return quiz

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
