import json
import logging
import pathlib
import unittest

from easynmt_ai import (
    AIContext,
    AIErrorCode,
    AIOrchestrator,
    AIResult,
    CurriculumEngine,
    GradingEngine,
    LearningContext,
    LessonEngine,
    QuizEngine,
)
from easynmt_ai.models import LearningPlan
from easynmt_ai.prompts import PromptSpec
from tests.lesson_fixtures import valid_lesson_proposal


class FakeGateway:
    def __init__(self, *responses, enabled=True):
        self.enabled = enabled
        self.responses = list(responses)
        self.calls = []

    def complete_custom(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, namespace, key):
        return self.values.get((namespace, key))

    def set(self, namespace, key, value, *, ttl_seconds=None):
        self.values[(namespace, key)] = dict(value)


def ai_response(payload, *, tokens=20):
    return AIResult(
        json.dumps(payload),
        "openai",
        response_id="resp-test",
        usage={"input_tokens": 10, "output_tokens": 10, "total_tokens": tokens},
    )


CURRICULUM_PAYLOAD = {
    "id": "curriculum-math-170",
    "subject": "math",
    "goal_score": 170,
    "plans": [
        {
            "id": "lesson-1",
            "title": "Linear equations",
            "objective": "Solve one-variable equations",
            "order": 1,
            "difficulty": "foundation",
            "estimated_minutes": 35,
            "prerequisite_ids": [],
        }
    ],
    "rationale": "Start with a prerequisite topic.",
}

LESSON_PAYLOAD = valid_lesson_proposal()

QUIZ_PAYLOAD = {
    "id": "quiz-1",
    "title": "Linear equations check",
    "lesson_id": "lesson-1",
    "questions": [
        {
            "id": "q1",
            "prompt": "Solve 2x = 8",
            "answer_type": "short_text",
            "options": [],
            "correct_answer": "4",
            "explanation": "Divide both sides by 2.",
            "points": 1,
        }
    ],
    "passing_percentage": 60,
}

GRADE_PAYLOAD = {
    "score": 1,
    "max_score": 1,
    "percentage": 100,
    "passed": True,
    "feedback": [
        {
            "message": "Correct.",
            "kind": "correct",
            "question_id": "q1",
            "suggestion": "",
        }
    ],
    "weaknesses": [],
}


class AIFoundationArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.context = AIContext(
            user_id=42,
            subject="math",
            goal_score=170,
            current_lesson=1,
            completed_lessons=(1,),
            known_weaknesses=("fractions",),
            recent_mistakes=("2/3 + 1/3",),
            xp=120,
            language="uk",
            difficulty="foundation",
            available_tokens=600,
        )

    @staticmethod
    def prompt():
        return PromptSpec(
            instructions="Return a test object.",
            user_input="test",
            schema_name="test_object",
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
        )

    def test_shared_context_preserves_legacy_tutor_compatibility(self):
        legacy = LearningContext(
            user_id=7,
            subject_key="history",
            goal="190",
            lesson_id=3,
        )
        self.assertEqual(legacy.subject, "history")
        self.assertEqual(legacy.goal_score, 190)
        self.assertEqual(legacy.current_lesson, 3)
        self.assertEqual(self.context.for_prompt()["known_weaknesses"], ["fractions"])

    def test_all_engine_interfaces_return_typed_models(self):
        gateway = FakeGateway(
            AIResult(
                "",
                "offline",
                "provider unavailable",
                error_code="disabled",
            ),
            ai_response(LESSON_PAYLOAD),
            ai_response(QUIZ_PAYLOAD),
            ai_response(GRADE_PAYLOAD),
        )
        orchestrator = AIOrchestrator(_gateway=gateway)

        curriculum = CurriculumEngine(orchestrator).generate(self.context)
        self.assertTrue(curriculum.success)
        self.assertTrue(curriculum.fallback_used)
        plan = LearningPlan.from_dict(CURRICULUM_PAYLOAD["plans"][0])

        lesson = LessonEngine(orchestrator).generate(self.context, plan)
        self.assertTrue(lesson.success)

        quiz = QuizEngine(orchestrator).generate(self.context, lesson.value, question_count=1)
        self.assertTrue(quiz.success)

        grade = GradingEngine(orchestrator).grade(self.context, quiz.value, {"q1": "4"})
        self.assertTrue(grade.success)
        self.assertTrue(grade.value.passed)
        self.assertEqual([call["metadata"]["engine"] for call in gateway.calls], [
            "curriculum", "lesson", "quiz", "grading",
        ])

    def test_lesson_generation_is_cache_ready(self):
        gateway = FakeGateway(ai_response(LESSON_PAYLOAD))
        cache = MemoryCache()
        orchestrator = AIOrchestrator(_gateway=gateway, cache=cache)
        plan = LearningPlan.from_dict(CURRICULUM_PAYLOAD["plans"][0])
        engine = LessonEngine(orchestrator)

        first = engine.generate(self.context, plan)
        second = engine.generate(self.context, plan)

        self.assertTrue(first.success)
        self.assertFalse(first.cached)
        self.assertTrue(second.success)
        self.assertTrue(second.cached)
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(gateway.calls[0]["max_output_tokens"], 600)

    def test_invalid_json_returns_structured_error_and_failure_log(self):
        gateway = FakeGateway(AIResult("not-json", "openai", usage={"total_tokens": 3}))
        logger = logging.getLogger("tests.easynmt.ai.invalid_json")
        orchestrator = AIOrchestrator(_gateway=gateway, logger=logger)

        with self.assertLogs(logger, level="INFO") as captured:
            result = orchestrator.execute_structured(
                engine_name="test_engine",
                context=self.context,
                prompt=self.prompt(),
                parser=dict,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.error.code, AIErrorCode.INVALID_JSON)
        self.assertFalse(captured.records[-1].ai_success)
        self.assertEqual(captured.records[-1].ai_engine, "test_engine")
        self.assertEqual(captured.records[-1].ai_user_id, 42)
        self.assertEqual(captured.records[-1].ai_token_usage, 3)

    def test_provider_failures_return_stable_error_codes(self):
        failures = (
            (AIResult("", "error", "rate limited", error_code="rate_limit", retryable=True), AIErrorCode.RATE_LIMIT),
            (AIResult("", "error", "empty", error_code="empty_response", retryable=True), AIErrorCode.EMPTY_RESPONSE),
            (TimeoutError("slow provider"), AIErrorCode.TIMEOUT),
        )
        for provider_result, expected_code in failures:
            with self.subTest(expected_code=expected_code):
                logger = logging.getLogger(f"tests.easynmt.ai.failure.{expected_code.value}")
                logger.handlers = [logging.NullHandler()]
                logger.propagate = False
                orchestrator = AIOrchestrator(
                    _gateway=FakeGateway(provider_result),
                    logger=logger,
                )
                result = orchestrator.execute_structured(
                    engine_name="test_engine",
                    context=self.context,
                    prompt=self.prompt(),
                    parser=dict,
                )
                self.assertFalse(result.success)
                self.assertEqual(result.error.code, expected_code)

    def test_only_orchestrator_owns_the_openai_adapter(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source_files = [
            path for path in root.rglob("*.py")
            if ".venv" not in path.parts and "tests" not in path.parts
        ]
        sdk_importers = []
        provider_users = []
        for path in source_files:
            source = path.read_text(encoding="utf-8")
            relative = path.relative_to(root).as_posix()
            if "from openai import" in source or "import openai" in source:
                sdk_importers.append(relative)
            if "OpenAIResponsesProvider" in source:
                provider_users.append(relative)

        self.assertEqual(sdk_importers, ["easynmt_ai/service.py"])
        self.assertEqual(
            sorted(provider_users),
            ["easynmt_ai/orchestrator.py", "easynmt_ai/service.py"],
        )
        app_source = (root / "app.py").read_text(encoding="utf-8")
        vision_source = (root / "vision_grading_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("ai_provider", app_source)
        self.assertNotIn("complete_custom", app_source)
        self.assertNotIn("complete_custom", vision_source)


if __name__ == "__main__":
    unittest.main()
