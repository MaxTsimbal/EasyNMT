from __future__ import annotations

import re
import uuid
from typing import Iterator

from .repository import AIRepository
from .schemas import AIRequest, AIResult, AIStreamEvent
from .service import OpenAIResponsesProvider


class AIOrchestrator:
    def __init__(self, provider: OpenAIResponsesProvider, repository: AIRepository):
        self.provider = provider
        self.repository = repository

    @property
    def enabled(self) -> bool:
        return self.provider.enabled

    @staticmethod
    def clean_text(value: object) -> str:
        text = str(value or "").strip()
        return re.sub(r"^\s*(?:Easy|Ізі)\s*:\s*", "", text, flags=re.IGNORECASE).strip()

    @staticmethod
    def new_message_id(prefix: str = "msg") -> str:
        return f"{prefix}-{uuid.uuid4()}"

    def prepare(self, request: AIRequest) -> None:
        title = request.question.strip().replace("\n", " ")[:46]
        if len(request.question.strip()) > 46:
            title = f"{title.rstrip()}…"
        self.repository.upsert_conversation(
            user_id=request.context.user_id,
            conversation_id=request.conversation_id,
            title=title or "Нова розмова",
            subject=request.context.subject_key,
            lesson_id=request.context.lesson_id,
            response_mode=request.context.response_mode,
        )
        self.repository.add_message(
            message_id=request.user_message_id,
            conversation_id=request.conversation_id,
            user_id=request.context.user_id,
            role="user",
            content=request.question,
            provider_mode="user",
            metadata={"attachment_ids": [item.id for item in request.attachments]},
        )
        self.repository.attach_to_message(
            user_id=request.context.user_id,
            attachment_ids=[item.id for item in request.attachments],
            message_id=request.user_message_id,
            conversation_id=request.conversation_id,
        )

    def complete(self, request: AIRequest) -> AIResult:
        self.prepare(request)
        result = self.provider.complete(request)
        result.text = self.clean_text(result.text)
        self.repository.add_message(
            message_id=request.assistant_message_id,
            conversation_id=request.conversation_id,
            user_id=request.context.user_id,
            role="assistant",
            content=result.text,
            provider_mode=result.mode,
            response_id=result.response_id,
            metadata={"usage": result.usage or {}},
        )
        return result

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        self.prepare(request)
        final_text = ""
        final_mode = "demo"
        response_id = None
        usage = None
        fallback_error = None

        for event in self.provider.stream(request):
            if event.type == "delta":
                final_text += str(event.data.get("text", ""))
                yield event
            elif event.type == "completed":
                final_text = str(event.data.get("text", final_text))
                final_mode = str(event.data.get("mode", "openai"))
                response_id = event.data.get("response_id")
                usage = event.data.get("usage")
            elif event.type == "fallback":
                fallback_text = self.clean_text(event.data.get("text", request.fallback))
                fallback_error = event.data.get("error")
                final_text = fallback_text
                final_mode = "demo"
                yield AIStreamEvent("fallback", {"text": fallback_text, "error": fallback_error})

        final_text = self.clean_text(final_text or request.fallback)
        self.repository.add_message(
            message_id=request.assistant_message_id,
            conversation_id=request.conversation_id,
            user_id=request.context.user_id,
            role="assistant",
            content=final_text,
            provider_mode=final_mode,
            response_id=response_id,
            metadata={"usage": usage or {}, "fallback_error": fallback_error},
        )
        yield AIStreamEvent("done", {
            "text": final_text,
            "mode": final_mode,
            "response_id": response_id,
            "usage": usage,
            "error": fallback_error,
            "message_id": request.assistant_message_id,
        })
