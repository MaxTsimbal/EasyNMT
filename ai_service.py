import os
from dataclasses import dataclass
from typing import Optional, Sequence

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
    ) -> AIResult:
        if not self.enabled:
            return AIResult(fallback, "demo")

        prompt_parts = [EASY_TUTOR_SYSTEM_PROMPT, GRADING_STYLE_PROMPT]
        if lesson_context:
            prompt_parts.insert(1, LESSON_STYLE_PROMPT)
        system_prompt = "\n\n".join(prompt_parts)

        history_lines = []
        for item in list(conversation_history or [])[-8:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            text = str(item.get("text", "")).strip()
            if role not in {"user", "assistant"} or not text:
                continue
            speaker = "Учень" if role == "user" else "Easy"
            history_lines.append(f"{speaker}: {text[:1000]}")

        history_context = ""
        if history_lines:
            history_context = (
                "\nКороткий контекст поточної розмови. Врахуй його, але не повторюй дослівно:\n"
                + "\n".join(history_lines)
                + "\n"
            )

        if lesson_context:
            user_prompt = (
                f"Предмет: {subject}.\n"
                f"Поточна тема уроку: {lesson_title}.\n"
                f"Мета уроку: {lesson_goal}.\n"
                f"{history_context}"
                f"Нове питання учня: {question}"
            )
        else:
            user_prompt = (
                f"Напрям підготовки учня: {subject}.\n"
                "Зараз Easy працює як окремий універсальний помічник, без прив’язки до конкретного уроку.\n"
                f"{history_context}"
                f"Нове питання учня: {question}"
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
