from __future__ import annotations

import os
from typing import Iterator

from .attachments import image_to_data_url
from .prompts import build_instructions, build_user_input
from .schemas import AIRequest, AIResult, AIStreamEvent

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class OpenAIResponsesProvider:
    """Single OpenAI gateway. The rest of EasyNMT never imports the SDK directly."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        self.vision_model = os.getenv("OPENAI_VISION_MODEL", self.model).strip() or self.model
        self.max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "900"))
        self.timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))
        self.max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
        self.store_responses = os.getenv("OPENAI_STORE_RESPONSES", "0") == "1"
        self.client = (
            OpenAI(api_key=self.api_key, timeout=self.timeout, max_retries=self.max_retries)
            if self.api_key and OpenAI
            else None
        )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def _request_kwargs(self, request: AIRequest, *, stream: bool = False) -> dict:
        input_items = build_user_input(request.question, request.history)
        if request.attachments:
            current = input_items[-1]
            content = [{"type": "input_text", "text": request.question}]
            for attachment in request.attachments:
                if attachment.kind == "image":
                    content.append({
                        "type": "input_image",
                        "image_url": image_to_data_url(attachment),
                        "detail": "auto",
                    })
            current["content"] = content

        return {
            "model": self.vision_model if request.attachments else self.model,
            "instructions": build_instructions(
                request.context,
                question=request.question,
                history=request.history,
                has_images=bool(request.attachments),
            ),
            "input": input_items,
            "max_output_tokens": self.max_output_tokens,
            "store": self.store_responses,
            "stream": stream,
            "metadata": {
                "app": "EasyNMT",
                "conversation_id": request.conversation_id[:64],
                "subject": request.context.subject_key[:32],
                "mode": request.context.response_mode[:16],
            },
        }


    @staticmethod
    def _usage_dict(response: object) -> dict | None:
        usage_obj = getattr(response, "usage", None)
        return usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else None

    def complete_custom(
        self,
        *,
        instructions: str,
        text: str,
        attachments: tuple = (),
        model: str | None = None,
        max_output_tokens: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AIResult:
        """Run a specialized Responses API task through the shared gateway.

        Used by grading and future lesson/test engines so no other module needs
        to import or configure the OpenAI SDK.
        """
        if not self.enabled:
            return AIResult("", "demo", "OpenAI is not configured")

        content = [{"type": "input_text", "text": text}]
        for attachment in attachments:
            if getattr(attachment, "kind", "") == "image":
                content.append({
                    "type": "input_image",
                    "image_url": image_to_data_url(attachment),
                    "detail": "auto",
                })

        kwargs = {
            "model": model or (self.vision_model if attachments else self.model),
            "instructions": instructions,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": max_output_tokens or self.max_output_tokens,
            "store": self.store_responses,
        }
        if metadata:
            kwargs["metadata"] = {
                str(key)[:64]: str(value)[:512]
                for key, value in metadata.items()
                if value is not None
            }

        try:
            response = self.client.responses.create(**kwargs)
            output = str(getattr(response, "output_text", "") or "").strip()
            if not output:
                return AIResult("", "demo", "OpenAI returned an empty response")
            return AIResult(
                text=output,
                mode="openai",
                response_id=str(getattr(response, "id", "") or "") or None,
                usage=self._usage_dict(response),
            )
        except Exception as exc:
            return AIResult("", "error", str(exc))

    def complete(self, request: AIRequest) -> AIResult:
        if not self.enabled:
            return AIResult(request.fallback, "demo")
        try:
            response = self.client.responses.create(**self._request_kwargs(request))
            text = str(getattr(response, "output_text", "") or "").strip()
            if not text:
                return AIResult(request.fallback, "demo", "OpenAI повернув порожню відповідь")
            usage = self._usage_dict(response)
            return AIResult(
                text=text,
                mode="openai",
                response_id=str(getattr(response, "id", "") or "") or None,
                usage=usage,
            )
        except Exception as exc:
            return AIResult(request.fallback, "demo", str(exc))

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        if not self.enabled:
            yield AIStreamEvent("fallback", {"text": request.fallback, "mode": "demo"})
            return

        response_id = None
        usage = None
        collected: list[str] = []
        try:
            stream = self.client.responses.create(**self._request_kwargs(request, stream=True))
            for event in stream:
                event_type = str(getattr(event, "type", "") or "")
                if event_type == "response.created":
                    response = getattr(event, "response", None)
                    response_id = str(getattr(response, "id", "") or "") or response_id
                elif event_type == "response.output_text.delta":
                    delta = str(getattr(event, "delta", "") or "")
                    if delta:
                        collected.append(delta)
                        yield AIStreamEvent("delta", {"text": delta})
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    response_id = str(getattr(response, "id", "") or "") or response_id
                    usage = self._usage_dict(response)
                elif event_type == "error":
                    error = getattr(event, "error", None)
                    raise RuntimeError(str(getattr(error, "message", "") or "OpenAI streaming error"))

            text = "".join(collected).strip()
            if not text:
                yield AIStreamEvent("fallback", {"text": request.fallback, "mode": "demo", "error": "empty_response"})
                return
            yield AIStreamEvent("completed", {
                "text": text,
                "mode": "openai",
                "response_id": response_id,
                "usage": usage,
            })
        except Exception as exc:
            partial = "".join(collected).strip()
            if partial:
                yield AIStreamEvent("completed", {
                    "text": partial,
                    "mode": "demo",
                    "response_id": response_id,
                    "usage": usage,
                    "error": str(exc),
                })
            else:
                yield AIStreamEvent("fallback", {"text": request.fallback, "mode": "demo", "error": str(exc)})
