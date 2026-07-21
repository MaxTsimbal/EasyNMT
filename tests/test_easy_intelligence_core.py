from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from easynmt_ai.intelligence import (
    build_execution_plan,
    build_learner_memory,
    polish_tutor_answer,
)
from easynmt_ai.prompts import build_instructions
from easynmt_ai.repository import AIRepository
from easynmt_ai.schemas import (
    AIRequest,
    AttachmentRef,
    LearnerMemory,
    LearningContext,
    TutorExecutionPlan,
)
from easynmt_ai.service import OpenAIResponsesProvider


class EasyIntelligenceCoreTests(unittest.TestCase):
    def context(self, *, mode: str = "explain", available_tokens: int = 2400) -> LearningContext:
        return LearningContext(
            user_id=7,
            subject="math",
            subject_key="math",
            subject_name="Математика",
            user_name="Учень",
            goal="180",
            goal_score=180,
            response_mode=mode,
            available_tokens=available_tokens,
            lesson_context=True,
            lesson_id=4,
            lesson_title="Системи рівнянь",
            lesson_goal="Навчитися розв’язувати системи двох рівнянь",
            known_weaknesses=("дроби",),
            recent_mistakes=("Помилка під час перенесення доданка",),
        )

    def request(
        self,
        *,
        context: LearningContext | None = None,
        plan: TutorExecutionPlan | None = None,
        memory: LearnerMemory | None = None,
        attachments: tuple[AttachmentRef, ...] = (),
    ) -> AIRequest:
        return AIRequest(
            question="Поясни цей крок",
            context=context or self.context(),
            fallback="Локальна відповідь",
            conversation_id="conversation-test",
            user_message_id="user-test",
            assistant_message_id="assistant-test",
            learner_memory=memory or LearnerMemory(),
            execution_plan=plan or TutorExecutionPlan(),
            attachments=attachments,
        )

    def test_short_concise_question_uses_fast_profile(self):
        plan = build_execution_plan(
            question="Коротко: що таке корінь рівняння?",
            history=(),
            context=self.context(mode="concise"),
            has_images=False,
        )
        self.assertEqual(plan.profile, "fast")
        self.assertEqual(plan.reasoning_effort, "minimal")
        self.assertEqual(plan.verbosity, "low")
        self.assertLessEqual(plan.max_output_tokens, 480)

    def test_complex_solution_uses_deep_profile(self):
        plan = build_execution_plan(
            question=(
                "Розв’яжи покроково систему рівнянь x + y = 7; "
                "2x - y = 5, обґрунтуй кожен крок і перевір результат."
            ),
            history=({"role": "user", "text": "Я не зрозумів попередній спосіб"},),
            context=self.context(),
            has_images=False,
        )
        self.assertEqual(plan.profile, "deep")
        self.assertIn(plan.reasoning_effort, {"medium", "high"})
        self.assertGreaterEqual(plan.complexity_score, 5)
        self.assertGreater(plan.max_output_tokens, 900)

    def test_image_request_uses_vision_profile_and_model(self):
        plan = build_execution_plan(
            question="Перевір моє розв’язання на фото",
            history=(),
            context=self.context(),
            has_images=True,
        )
        provider = OpenAIResponsesProvider({
            "OPENAI_MODEL": "gpt-4o-mini",
            "OPENAI_TUTOR_MODEL": "gpt-4o-mini",
            "OPENAI_VISION_MODEL": "vision-model-test",
        })
        attachment = AttachmentRef(
            id="img-1",
            original_name="solution.png",
            mime_type="image/png",
            size_bytes=10,
            stored_path="/tmp/unused.png",
        )
        request = self.request(plan=plan, attachments=(attachment,))
        self.assertEqual(plan.profile, "vision")
        self.assertEqual(provider._model_for_request(request), "vision-model-test")

    def test_learner_memory_changes_style_after_explicit_retry_signal(self):
        memory = build_learner_memory(
            self.context(),
            ({"role": "user", "text": "Поясни по кроках"},),
            question="Я все одно не зрозумів, поясни простіше й інакше",
            persisted={
                "preferred_style": "adaptive",
                "needs_step_by_step": False,
                "explanation_failures": 1,
                "last_focus": "Лінійні рівняння",
            },
        )
        self.assertEqual(memory.preferred_style, "simple")
        self.assertTrue(memory.needs_step_by_step)
        self.assertEqual(memory.explanation_failures, 2)
        self.assertIn("Лінійні рівняння", memory.focus_topics)

    def test_repository_persists_explicit_teaching_preferences(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "memory.sqlite3")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            conn.execute("INSERT INTO users (id, name) VALUES (7, 'Test learner')")
            conn.commit()
            conn.close()

            repository = AIRepository(db_path)
            repository.ensure_schema()
            repository.observe_learner_signal(
                user_id=7,
                subject="math",
                message="Я все одно не зрозумів. Поясни з нуля по кроках.",
                response_mode="explain",
                lesson_title="Системи рівнянь",
            )
            stored = repository.get_learner_memory(user_id=7, subject="math")

        self.assertEqual(stored["preferred_style"], "simple")
        self.assertTrue(stored["needs_step_by_step"])
        self.assertEqual(stored["explanation_failures"], 1)
        self.assertEqual(stored["last_focus"], "Системи рівнянь")

    def test_prompt_receives_memory_and_plan_without_provider_details(self):
        memory = LearnerMemory(
            preferred_style="guided",
            needs_step_by_step=True,
            focus_topics=("дроби",),
        )
        plan = TutorExecutionPlan(
            profile="deep",
            reasoning_effort="medium",
            verbosity="high",
            max_output_tokens=1200,
            complexity_score=7,
            intent="розв’язати задачу",
        )
        prompt = build_instructions(
            self.context(),
            question="Дай підказку",
            history=(),
            learner_memory=memory,
            execution_plan=plan,
        )
        self.assertIn("Навчальна пам’ять Easy", prompt)
        self.assertIn("веди підказками", prompt)
        self.assertIn("План цієї відповіді Easy", prompt)
        self.assertNotIn("gpt-", prompt.lower())
        self.assertNotIn("api_key", prompt.lower())

    def test_provider_adds_reasoning_controls_only_for_compatible_model(self):
        deep_plan = TutorExecutionPlan(
            profile="deep",
            reasoning_effort="high",
            verbosity="high",
            max_output_tokens=1300,
            complexity_score=8,
        )
        reasoning_provider = OpenAIResponsesProvider({
            "OPENAI_MODEL": "gpt-4o-mini",
            "OPENAI_TUTOR_REASONING_MODEL": "gpt-5-test",
            "OPENAI_MAX_OUTPUT_TOKENS": 1600,
        })
        reasoning_kwargs = reasoning_provider._request_kwargs(
            self.request(plan=deep_plan)
        )
        self.assertEqual(reasoning_kwargs["model"], "gpt-5-test")
        self.assertEqual(reasoning_kwargs["reasoning"], {"effort": "high"})
        self.assertEqual(reasoning_kwargs["text"], {"verbosity": "high"})

        o_series_provider = OpenAIResponsesProvider({
            "OPENAI_MODEL": "gpt-4o-mini",
            "OPENAI_TUTOR_REASONING_MODEL": "o3-test",
            "OPENAI_MAX_OUTPUT_TOKENS": 1600,
        })
        o_series_kwargs = o_series_provider._request_kwargs(
            self.request(plan=TutorExecutionPlan(profile="deep", reasoning_effort="minimal"))
        )
        self.assertEqual(o_series_kwargs["reasoning"], {"effort": "low"})
        self.assertNotIn("text", o_series_kwargs)

        balanced_provider = OpenAIResponsesProvider({
            "OPENAI_MODEL": "gpt-4o-mini",
            "OPENAI_TUTOR_MODEL": "gpt-4o-mini",
        })
        balanced_kwargs = balanced_provider._request_kwargs(self.request())
        self.assertNotIn("reasoning", balanced_kwargs)
        self.assertNotIn("text", balanced_kwargs)

    def test_answer_polisher_removes_canned_shell_but_keeps_content(self):
        answer = polish_tutor_answer(
            "Звичайно! Рівняння розв’язуємо у два кроки.\n\n"
            "1. Переносимо доданок.\n2. Ділимо на коефіцієнт.\n\n"
            "Якщо маєш ще питання, звертайся."
        )
        self.assertTrue(answer.startswith("Рівняння розв’язуємо"))
        self.assertIn("Переносимо доданок", answer)
        self.assertNotIn("Звичайно", answer)
        self.assertNotIn("звертайся", answer.lower())


if __name__ == "__main__":
    unittest.main()
