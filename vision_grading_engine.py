"""Grades photographed handwritten solutions through the shared EasyNMT AI gateway."""
from __future__ import annotations

import json
import mimetypes
import os
import re
from typing import Any

from easynmt_ai.schemas import AttachmentRef
from easynmt_ai.service import OpenAIResponsesProvider


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


class VisionGradingEngine:
    """Photo grading facade. OpenAI SDK access remains centralized in service.py."""

    def __init__(self, provider: OpenAIResponsesProvider | None = None):
        self.provider = provider or OpenAIResponsesProvider()

    @property
    def enabled(self) -> bool:
        return self.provider.enabled

    def grade(self, *, image_path: str, question: str, correct_answer: str, reference_solution: str) -> dict[str, Any]:
        if not self.enabled:
            return {
                "score": 0,
                "is_correct": False,
                "message": "Фото збережено, але AI-перевірка зараз недоступна. Перевір, чи OPENAI_API_KEY додано в Railway Variables.",
                "correct_step": reference_solution or correct_answer,
                "error_box": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.15},
                "mode": "demo",
            }

        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        attachment = AttachmentRef(
            id="grading-image",
            original_name=os.path.basename(image_path) or "solution.jpg",
            mime_type=mime,
            size_bytes=os.path.getsize(image_path),
            stored_path=image_path,
            kind="image",
        )
        instructions = (
            "Ти перевіряєш рукописне розв'язання українського школяра. "
            "Оціни лише видимий хід розв'язання. Не вигадуй нерозбірливі символи. "
            "Поверни ЛИШЕ JSON: score (0..3), is_correct, message, correct_step, "
            "error_box з x,y,width,height у частках від 0 до 1. "
            "score: 1 за правильний підхід, 1 за правильні обчислення, 1 за правильну відповідь. "
            "Якщо все правильно, error_box може бути null. Пояснюй просто, без шаблонних вступів."
        )
        prompt = (
            f"Завдання: {question}\n"
            f"Очікувана відповідь: {correct_answer}\n"
            f"Орієнтовний правильний хід: {reference_solution}\n"
            "Знайди першу змістову помилку та покажи, як виправити саме цей крок."
        )
        result = self.provider.complete_custom(
            instructions=instructions,
            text=prompt,
            attachments=(attachment,),
            model=self.provider.vision_model,
            max_output_tokens=500,
            metadata={"app": "EasyNMT", "task": "photo_grading"},
        )
        if result.mode != "openai":
            return {
                "score": 0,
                "is_correct": False,
                "message": "Не вдалося перевірити фото. Спробуй зробити чіткіший знімок без тіней.",
                "correct_step": reference_solution or correct_answer,
                "error_box": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.15},
                "mode": "error",
                "error": result.error or "AI grading failed",
            }

        parsed = _extract_json(result.text)
        try:
            score = max(0, min(3, int(parsed.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        return {
            "score": score,
            "is_correct": bool(parsed.get("is_correct", score == 3)),
            "message": str(parsed.get("message") or "Перевір позначений крок."),
            "correct_step": str(parsed.get("correct_step") or reference_solution or correct_answer),
            "error_box": parsed.get("error_box"),
            "mode": "openai",
        }
