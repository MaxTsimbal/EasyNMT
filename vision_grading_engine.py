"""Compatibility facade for the existing photographed-solution workflow."""
from __future__ import annotations

import mimetypes
import os
from typing import Any, Mapping

from easynmt_ai import AIContext, AIOrchestrator
from easynmt_ai.prompts.grading import build_vision_grading_prompt
from easynmt_ai.schemas import AttachmentRef


class VisionGradingEngine:
    """Grade a solution photo through the central AI orchestrator."""

    name = "grading.vision"

    def __init__(self, orchestrator: AIOrchestrator):
        self.orchestrator = orchestrator

    @property
    def enabled(self) -> bool:
        return self.orchestrator.enabled

    @staticmethod
    def _offline(reference_solution: str, correct_answer: str) -> dict[str, Any]:
        return {
            "score": 0,
            "is_correct": False,
            "message": (
                "Фото збережено, але AI-перевірка зараз недоступна. "
                "Перевір, чи OPENAI_API_KEY додано в Railway Variables."
            ),
            "correct_step": reference_solution or correct_answer,
            "error_box": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.15},
            "mode": "offline",
        }

    def grade(
        self,
        *,
        user_id: int,
        image_path: str,
        question: str,
        correct_answer: str,
        reference_solution: str,
        subject: str = "none",
    ) -> dict[str, Any]:
        if not self.enabled:
            return self._offline(reference_solution, correct_answer)

        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        attachment = AttachmentRef(
            id="grading-image",
            original_name=os.path.basename(image_path) or "solution.jpg",
            mime_type=mime,
            size_bytes=os.path.getsize(image_path),
            stored_path=image_path,
            kind="image",
        )
        context = AIContext(
            user_id=user_id,
            subject=subject,
            language="uk",
            available_tokens=500,
        )
        result = self.orchestrator.execute_structured(
            engine_name=self.name,
            context=context,
            prompt=build_vision_grading_prompt(
                question=question,
                correct_answer=correct_answer,
                reference_solution=reference_solution,
            ),
            attachments=(attachment,),
            parser=lambda payload: dict(payload),
        )
        if not result.success:
            error = result.error
            return {
                "score": 0,
                "is_correct": False,
                "message": "Не вдалося перевірити фото. Спробуй зробити чіткіший знімок без тіней.",
                "correct_step": reference_solution or correct_answer,
                "error_box": {"x": 0.05, "y": 0.05, "width": 0.9, "height": 0.15},
                "mode": "error",
                "error": error.message if error else "AI grading failed",
                "error_code": error.code.value if error else "internal_error",
            }

        parsed: Mapping[str, Any] = result.value or {}
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
