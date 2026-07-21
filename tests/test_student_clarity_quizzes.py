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


class ProductionExamQuizTests(unittest.TestCase):
    def _english_lesson(self, topic_id: str = "english.grammar.present_past") -> Lesson:
        payload = valid_lesson_proposal(competency_count=2)
        payload.update({
            "id": f"lesson-{topic_id.replace('.', '-')}",
            "curriculum_id": "curriculum-english-v1",
            "curriculum_unit_id": f"unit-{topic_id.replace('.', '-')}",
            "topic_id": topic_id,
            "title": "Практична англійська",
            "subject": "english",
            "difficulty": "foundation",
            "estimated_minutes": 24,
            "objectives": ("Застосовувати англійську в контексті",),
            "competencies": ("Вибір форми", "Практичні трансформації"),
            "generation_metadata": {
                "source": "test",
                "request_fingerprint": "production-exam-regression",
                "prompt_version": "test",
                "schema_version": "lesson.v1",
                "model_identifier": "fixture",
                "generated_at": "2026-07-21T12:00:00+00:00",
            },
        })
        return Lesson.from_dict(payload)

    def test_reviewed_task_bank_still_covers_every_published_topic(self):
        published_topics: set[str] = set()
        for path in sorted(DATA_DIR.glob("*_v1.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            published_topics.update(item["id"] for item in payload["topics"])

        self.assertEqual(len(published_topics), 75)
        self.assertEqual(set(TOPIC_TASKS), published_topics)

    def test_english_quiz_is_practical_instead_of_rule_recall(self):
        quiz = build_deterministic_quiz(self._english_lesson(), variant_seed="attempt-one")

        self.assertEqual([q.answer_type for q in quiz.questions[:4]], ["choice"] * 4)
        self.assertEqual([q.points for q in quiz.questions], [1] * 4 + [2] * 4 + [3] * 4)
        self.assertIn("заперечення", quiz.questions[4].instruction.lower())
        self.assertIn("питання", quiz.questions[5].instruction.lower())
        self.assertIn("слів", quiz.questions[6].instruction.lower())
        self.assertIn("виправ", quiz.questions[7].instruction.lower())
        self.assertTrue(all(q.grading_mode == "rubric" for q in quiz.questions[8:]))
        self.assertTrue(all(len(q.scoring_parts) == 3 for q in quiz.questions[8:]))
        self.assertFalse(any("поясни правило" in q.task.lower() for q in quiz.questions))
        self.assertEqual(quiz.schema_version, "quiz.v1.5-photo-final")

    def test_each_attempt_can_receive_a_different_server_gradeable_variant(self):
        lesson = self._english_lesson()
        first = build_deterministic_quiz(lesson, variant_seed="attempt-a")
        second = build_deterministic_quiz(lesson, variant_seed="attempt-b")

        self.assertEqual(first.id, second.id)
        self.assertNotEqual([q.task for q in first.questions], [q.task for q in second.questions])
        self.assertEqual(first.to_dict(), build_deterministic_quiz(lesson, variant_seed="attempt-a").to_dict())

    def test_public_quiz_exposes_helpful_copy_but_never_grading_secrets(self):
        quiz = build_deterministic_quiz(self._english_lesson(), variant_seed="public")
        written = quiz.to_public_dict()["questions"][8]

        self.assertTrue(written["skill"])
        self.assertTrue(written["input_placeholder"])
        for secret in (
            "correct_answer",
            "accepted_answers",
            "keywords",
            "primary_answers",
            "secondary_answers",
            "scoring_parts",
            "grading_mode",
            "explanation",
        ):
            self.assertNotIn(secret, written)

    def test_old_quiz_snapshots_remain_readable(self):
        current = build_deterministic_quiz(self._english_lesson(), variant_seed="legacy")
        legacy_payload = current.to_dict()
        legacy_payload["schema_version"] = "quiz.v1.3-student-clarity"
        for question in legacy_payload["questions"]:
            for field in ("skill", "source_text", "input_placeholder", "scoring_parts", "review_tip"):
                question.pop(field, None)
            if question["grading_mode"] == "rubric":
                question["grading_mode"] = "solution"
                question["primary_answers"] = [question["correct_answer"]]
                question["secondary_answers"] = []

        restored = ProductionQuiz.from_dict(legacy_payload)
        self.assertEqual(restored.schema_version, "quiz.v1.3-student-clarity")
        self.assertTrue(all(not item.skill and not item.scoring_parts for item in restored.questions))

    def test_easy_receives_exercise_type_but_not_the_answer_key(self):
        lesson = self._english_lesson("english.reading.gist_detail")
        quiz = build_deterministic_quiz(lesson, variant_seed="reading")

        choice = quiz.questions[0]
        choice_context = quiz_prompt_context(lesson, choice, question_number=1)
        choice_serialized = json.dumps(choice_context, ensure_ascii=False)
        self.assertEqual(choice_context["skill"], choice.skill)
        self.assertEqual(choice_context["source_text"], choice.source_text)
        self.assertEqual(tuple(choice_context["visible_options"]), choice.options)
        self.assertNotIn("correct_answer", choice_serialized)
        self.assertNotIn("accepted_answers", choice_serialized)
        self.assertNotIn("scoring_parts", choice_serialized)

        written = quiz.questions[4]
        written_context = quiz_prompt_context(lesson, written, question_number=5)
        written_serialized = json.dumps(written_context, ensure_ascii=False)
        self.assertNotIn(written.correct_answer, written_serialized)
        self.assertNotIn("correct_answer", written_serialized)
        self.assertNotIn("accepted_answers", written_serialized)
        self.assertNotIn("scoring_parts", written_serialized)


if __name__ == "__main__":
    unittest.main()
