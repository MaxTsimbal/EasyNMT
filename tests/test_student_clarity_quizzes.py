from __future__ import annotations

import json
import pathlib
import unittest

from easynmt_ai import Lesson
from easynmt_core.contextual_easy import quiz_prompt_context
from easynmt_core.quizzes import ProductionQuiz, build_deterministic_quiz
from easynmt_core.quizzes.task_bank import TOPIC_TASKS
from tests.lesson_fixtures import valid_lesson_proposal


ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "easynmt_ai/curriculum/data"


class StudentClarityQuizTests(unittest.TestCase):
    def _lesson_with_abstract_english_examples(self) -> Lesson:
        payload = valid_lesson_proposal(competency_count=2)
        payload.update({
            "id": "lesson-present-past-clarity",
            "curriculum_id": "curriculum-english-v1",
            "curriculum_unit_id": "unit-present-past-clarity",
            "topic_id": "english.grammar.present_past",
            "title": "Present Simple, Present Continuous і минулі часи",
            "subject": "english",
            "difficulty": "foundation",
            "estimated_minutes": 24,
            "objectives": ("Розрізняти часові форми за контекстом",),
            "competencies": ("Вибір часу", "Пояснення часових маркерів"),
            "generation_metadata": {
                "source": "test",
                "request_fingerprint": "student-clarity-regression",
                "prompt_version": "test",
                "schema_version": "lesson.v1",
                "model_identifier": "fixture",
                "generated_at": "2026-07-20T12:00:00+00:00",
            },
        })
        abstract_labels = (
            "Вибір правильної часової форми в контексті речення.",
            "Complete an English language task using the lesson algorithm.",
            "Застосування правила та перевірка дистракторів у форматі НМТ.",
        )
        for index, example in enumerate(payload["worked_examples"]):
            example["id"] = f"abstract-{index + 1}"
            example["problem"] = abstract_labels[index]
            example["final_answer"] = "Правильний варіант"
            example["reasoning"] = "Застосовано схему з уроку."
            example["verification"] = "Підтверджено умовою."
        return Lesson.from_dict(payload)

    def test_reviewed_task_bank_covers_every_published_topic(self):
        published_topics: set[str] = set()
        for path in sorted(DATA_DIR.glob("*_v1.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            published_topics.update(item["id"] for item in payload["topics"])

        self.assertEqual(len(published_topics), 75)
        self.assertEqual(set(TOPIC_TASKS), published_topics)
        for topic_id, tasks in TOPIC_TASKS.items():
            with self.subTest(topic_id=topic_id):
                self.assertEqual(len(tasks), 3)
                self.assertEqual(len({item.task.casefold() for item in tasks}), 3)
                for item in tasks:
                    self.assertGreaterEqual(len(item.task), 12)
                    self.assertTrue(item.final_answer.strip())
                    self.assertTrue(item.reasoning.strip())
                    self.assertTrue(item.verification.strip())
                    lowered = item.task.casefold()
                    for abstract_phrase in (
                        "вибір правильної",
                        "розпізнавання основної",
                        "застосування правила",
                        "complete an english language task",
                        "дистрактор",
                    ):
                        self.assertNotIn(abstract_phrase, lowered)

    def test_abstract_labels_are_replaced_with_real_student_tasks(self):
        lesson = self._lesson_with_abstract_english_examples()
        quiz = build_deterministic_quiz(lesson)
        expected = TOPIC_TASKS[lesson.topic_id]

        self.assertEqual(quiz.questions[3].task, expected[0].task)
        self.assertEqual([question.task for question in quiz.questions[8:11]], [item.task for item in expected])
        forbidden = (
            "Вибір правильної часової форми",
            "Complete an English language task",
            "дистракторів у форматі НМТ",
        )
        for question in quiz.questions:
            with self.subTest(question=question.id):
                self.assertTrue(question.instruction)
                self.assertTrue(question.task)
                self.assertTrue(question.answer_format)
                self.assertFalse(any(phrase.casefold() in question.task.casefold() for phrase in forbidden))

    def test_public_quiz_has_clear_copy_but_never_answer_key(self):
        lesson = self._lesson_with_abstract_english_examples()
        quiz = build_deterministic_quiz(lesson)
        question = quiz.to_public_dict()["questions"][8]

        self.assertEqual(question["instruction"], "Виконай конкретне завдання.")
        self.assertTrue(question["task"])
        self.assertIn("Відповідь дає 2 бали", question["answer_format"])
        for secret in (
            "correct_answer",
            "accepted_answers",
            "keywords",
            "primary_answers",
            "secondary_answers",
            "explanation",
        ):
            self.assertNotIn(secret, question)

    def test_old_quiz_snapshots_remain_readable(self):
        lesson = self._lesson_with_abstract_english_examples()
        current = build_deterministic_quiz(lesson)
        legacy_payload = current.to_dict()
        legacy_payload["schema_version"] = "quiz.v1.2-contextual-easy"
        for question in legacy_payload["questions"]:
            question.pop("instruction", None)
            question.pop("task", None)
            question.pop("answer_format", None)

        restored = ProductionQuiz.from_dict(legacy_payload)
        self.assertEqual(restored.schema_version, "quiz.v1.2-contextual-easy")
        self.assertTrue(all(not item.instruction and not item.task and not item.answer_format for item in restored.questions))

    def test_easy_receives_the_visible_task_and_format_without_grading_secrets(self):
        lesson = self._lesson_with_abstract_english_examples()
        quiz = build_deterministic_quiz(lesson)
        question = quiz.questions[8]
        context = quiz_prompt_context(lesson, question, question_number=9)
        serialized = json.dumps(context, ensure_ascii=False)

        self.assertEqual(context["instruction"], question.instruction)
        self.assertEqual(context["task"], question.task)
        self.assertEqual(context["answer_format"], question.answer_format)
        self.assertNotIn(question.correct_answer, serialized)
        self.assertNotIn("accepted_answers", serialized)
        self.assertNotIn("grading_mode", serialized)


if __name__ == "__main__":
    unittest.main()
