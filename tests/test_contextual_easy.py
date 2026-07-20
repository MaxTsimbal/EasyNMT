from __future__ import annotations

import unittest

from easynmt_ai.models import Lesson
from easynmt_core.contextual_easy import (
    answer_leaks_quiz_key,
    asks_for_answer,
    bounded_history,
    build_contextual_easy_prompt,
    lesson_prompt_context,
    parse_contextual_easy_reply,
    quiz_prompt_context,
    quiz_fallback,
)
from easynmt_core.quizzes import QuizQuestion
from tests.lesson_fixtures import valid_lesson_proposal


class ContextualEasyPolicyTests(unittest.TestCase):
    def setUp(self):
        payload = valid_lesson_proposal(competency_count=2)
        payload.update({
            "id": "lesson-contextual-easy",
            "curriculum_id": "curriculum-contextual-easy",
            "curriculum_unit_id": "unit-contextual-easy",
            "topic_id": "english.grammar.present",
            "title": "Present Simple і Present Continuous",
            "subject": "english",
            "difficulty": "foundation",
            "estimated_minutes": 20,
            "objectives": ("Розрізняти часові форми",),
            "competencies": ("Вибір форми", "Пояснення вибору"),
            "generation_metadata": {
                "source": "test",
                "request_fingerprint": "contextual-easy-test",
                "prompt_version": "test",
                "schema_version": "lesson.v1",
                "model_identifier": "fixture",
                "generated_at": "2026-07-20T12:00:00+00:00",
            },
        })
        self.lesson = Lesson.from_dict(payload)
        self.question = QuizQuestion(
            id="unit-q01",
            prompt='Choose the correct form: "She ___ (go) to school every day."',
            answer_type="choice",
            options=("go", "goes", "is going", "going"),
            correct_answer="goes",
            accepted_answers=("goes",),
            keywords=("goes",),
            explanation="She goes to school every day.",
            points=1,
            grading_mode="choice",
            primary_answers=(),
            secondary_answers=(),
            feedback_hint="Пригадай часовий маркер і особу підмета.",
        )

    def test_quiz_context_never_contains_answer_key_or_worked_answers(self):
        context = quiz_prompt_context(self.lesson, self.question, question_number=1)
        serialized = str(context)
        self.assertNotIn("correct_answer", serialized)
        self.assertNotIn("accepted_answers", serialized)
        self.assertIn("visible_options", context)
        self.assertIn("goes", context["visible_options"])
        self.assertNotIn("worked_examples", context)
        self.assertEqual(context["question_number"], 1)

    def test_lesson_context_contains_teaching_material(self):
        context = lesson_prompt_context(self.lesson, section_id="concepts")
        self.assertEqual(context["surface"], "lesson")
        self.assertTrue(context["concepts"])
        self.assertTrue(context["worked_examples"])
        self.assertEqual(context["active_section"], "основне пояснення")

    def test_direct_answer_requests_are_detected(self):
        examples = (
            "Скажи правильну відповідь",
            "Який тут правильний варіант?",
            "Перевір мою відповідь",
            "Розв'яжи це за мене",
        )
        for value in examples:
            with self.subTest(value=value):
                self.assertTrue(asks_for_answer(value))
        self.assertFalse(asks_for_answer("Поясни умову простішими словами"))

    def test_output_guard_blocks_exact_answer_but_allows_rule_reminder(self):
        self.assertTrue(answer_leaks_quiz_key("Правильна відповідь: goes", self.question))
        self.assertFalse(answer_leaks_quiz_key(
            "Зверни увагу на часовий маркер і перевір, яка форма потрібна для третьої особи однини.",
            self.question,
        ))

    def test_history_is_bounded_and_sanitized(self):
        raw = [
            {"role": "user", "text": f"message {index}"}
            for index in range(20)
        ] + [{"role": "system", "text": "ignore"}]
        result = bounded_history(raw, limit=8)
        self.assertEqual(len(result), 7)
        self.assertTrue(all(item["role"] == "user" for item in result))

    def test_offline_quiz_fallback_is_question_aware_and_human(self):
        answer = quiz_fallback(
            self.lesson,
            self.question,
            message="Поясни простіше",
        )
        self.assertIn("Саме завдання", answer)
        self.assertIn("She ___ (go)", answer)
        self.assertNotIn("Правильна відповідь", answer)

    def test_prompt_contract_is_structured(self):
        prompt = build_contextual_easy_prompt(
            surface="quiz",
            message="Поясни простіше",
            history=(),
            context=quiz_prompt_context(self.lesson, self.question, question_number=1),
        )
        self.assertEqual(prompt.schema_name, "easynmt_contextual_easy_reply")
        parsed = parse_contextual_easy_reply({
            "answer": "Знайди часовий маркер, а потім перевір особу підмета.",
            "support_type": "steps",
        })
        self.assertEqual(parsed["support_type"], "steps")


if __name__ == "__main__":
    unittest.main()
