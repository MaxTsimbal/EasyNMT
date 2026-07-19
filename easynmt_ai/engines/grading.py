"""Grading engine: evaluates submitted answers and returns typed feedback."""
from __future__ import annotations

from typing import Mapping

from ..errors import EngineResult
from ..models import AIModelValidationError, GradeResult, Quiz
from ..prompts.grading import build_grading_prompt
from ..schemas import AIContext
from .base import AIEngine


class GradingEngine(AIEngine[GradeResult]):
    """Grade answers without awarding XP or finalizing a quiz attempt."""

    name = "grading"
    cache_namespace = "grading"

    def grade(
        self,
        context: AIContext,
        quiz: Quiz,
        answers: Mapping[str, str],
    ) -> EngineResult[GradeResult]:
        question_ids = {question.id for question in quiz.questions}
        unknown_ids = set(answers) - question_ids
        if unknown_ids:
            raise ValueError("answers contain unknown question IDs")
        normalized_answers = {
            question.id: str(answers.get(question.id, ""))
            for question in quiz.questions
        }
        prompt = build_grading_prompt(context, quiz, normalized_answers)

        def parse(payload):
            grade = GradeResult.from_dict(payload)
            expected_max = sum(question.points for question in quiz.questions)
            if grade.max_score != expected_max:
                raise AIModelValidationError("grade maximum does not match the quiz")
            expected_percentage = round((grade.score / expected_max) * 100)
            if grade.percentage != expected_percentage:
                raise AIModelValidationError("grade percentage is inconsistent")
            if grade.passed != (grade.percentage >= quiz.passing_percentage):
                raise AIModelValidationError("grade pass state is inconsistent")
            return grade

        return self.orchestrator.execute_structured(
            engine_name=self.name,
            context=context,
            prompt=prompt,
            parser=parse,
        )
