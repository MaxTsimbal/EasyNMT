import os
from dataclasses import dataclass
from typing import Optional

from prompts import EASY_TUTOR_SYSTEM_PROMPT, GRADING_STYLE_PROMPT, LESSON_STYLE_PROMPT

try:
    from openai import OpenAI
except ImportError:  # App can still run in demo mode before dependencies are installed.
    OpenAI = None


@dataclass
class AIResult:
    text: str
    mode: str
    error: Optional[str] = None


class EasyNMT_AI:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        self.max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "500"))
        self.client = OpenAI(api_key=self.api_key, timeout=25.0, max_retries=1) if self.api_key and OpenAI else None

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def answer(self, *, question: str, subject: str, lesson_title: str, lesson_goal: str, fallback: str) -> AIResult:
        if not self.enabled:
            return AIResult(fallback, "demo")
        system_prompt = "\n\n".join([EASY_TUTOR_SYSTEM_PROMPT, LESSON_STYLE_PROMPT, GRADING_STYLE_PROMPT])
        user_prompt = (
            f"Предмет: {subject}.\n"
            f"Поточна тема: {lesson_title}.\n"
            f"Мета уроку: {lesson_goal}.\n"
            f"Питання учня: {question}"
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=user_prompt,
                max_output_tokens=self.max_output_tokens,
            )
            text = (response.output_text or "").strip()
            if not text:
                return AIResult(fallback, "demo", "OpenAI повернув порожню відповідь")
            return AIResult(text, "openai")
        except Exception as exc:
            return AIResult(fallback, "demo", str(exc))
