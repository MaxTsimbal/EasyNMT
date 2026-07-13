"""Grades photographed handwritten solutions with OpenAI vision and a safe fallback."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from typing import Any

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


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
    def __init__(self):
        key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"
        self.client = OpenAI(api_key=key, timeout=45.0, max_retries=1) if key and OpenAI else None

    @property
    def enabled(self) -> bool:
        return self.client is not None

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
        with open(image_path, "rb") as file:
            data_url = f"data:{mime};base64,{base64.b64encode(file.read()).decode('ascii')}"

        instructions = (
            "Ти перевіряєш рукописне розв'язання українського школяра. "
            "Оціни лише видимий хід розв'язання. Не вигадуй нерозбірливі символи. "
            "Поверни ЛИШЕ JSON: score (0..3), is_correct, message, correct_step, "
            "error_box з x,y,width,height у частках від 0 до 1. "
            "score: 1 за правильний підхід, 1 за правильні обчислення, 1 за правильну відповідь. "
            "Якщо все правильно, error_box може бути null. Пояснюй просто, без фраз у стилі ChatGPT."
        )
        prompt = (
            f"Завдання: {question}\n"
            f"Очікувана відповідь: {correct_answer}\n"
            f"Орієнтовний правильний хід: {reference_solution}\n"
            "Знайди першу змістову помилку та покажи, як виправити саме цей крок."
        )
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=[{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }],
                max_output_tokens=500,
            )
            result = _extract_json(response.output_text)
            score = max(0, min(3, int(result.get("score", 0))))
            return {
                "score": score,
                "is_correct": bool(result.get("is_correct", score == 3)),
                "message": str(result.get("message") or "Перевір позначений крок."),
                "correct_step": str(result.get("correct_step") or reference_solution or correct_answer),
                "error_box": result.get("error_box"),
                "mode": "openai",
            }
        except Exception as exc:
            return {
                "score": 0,
                "is_correct": False,
                "message": "Не вдалося перевірити фото. Спробуй зробити чіткіший знімок без тіней.",
                "correct_step": reference_solution or correct_answer,
                "error_box": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.15},
                "mode": "error",
                "error": str(exc),
            }
