"""Compatibility facade for the new EasyNMT AI foundation.

Legacy lesson routes can keep calling EasyNMT_AI.answer(), while all OpenAI SDK
usage now lives in easynmt_ai.service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from easynmt_ai.prompts import build_instructions
from easynmt_ai.schemas import AIRequest, LearningContext
from easynmt_ai.service import OpenAIResponsesProvider


@dataclass
class AIResult:
    text: str
    mode: str
    error: Optional[str] = None
    response_id: Optional[str] = None


class EasyNMT_AI:
    def __init__(self):
        self.provider = OpenAIResponsesProvider()
        self.model = self.provider.model

    @property
    def enabled(self) -> bool:
        return self.provider.enabled

    def answer(
        self,
        *,
        question: str,
        subject: str,
        lesson_title: str = "",
        lesson_goal: str = "",
        fallback: str,
        lesson_context: bool = False,
        conversation_history: Optional[Sequence[dict]] = None,
        response_mode: str = "explain",
    ) -> AIResult:
        context = LearningContext(
            user_id=0,
            subject_name=subject,
            lesson_title=lesson_title,
            lesson_goal=lesson_goal,
            lesson_context=lesson_context,
            response_mode=response_mode,
        )
        request = AIRequest(
            question=question,
            context=context,
            history=conversation_history or (),
            fallback=fallback,
            conversation_id="legacy",
        )
        result = self.provider.complete(request)
        return AIResult(
            text=result.text,
            mode=result.mode,
            error=result.error,
            response_id=result.response_id,
        )
