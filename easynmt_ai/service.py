"""Internal OpenAI Responses API adapter.

Only :class:`easynmt_ai.orchestrator.AIOrchestrator` may instantiate or invoke
this module. Application routes and engines depend on the orchestrator instead.
"""
from __future__ import annotations

import os
import re
from typing import Any, Iterator, Mapping

from .attachments import image_to_data_url
from .intelligence import strip_generic_opening
from .prompts import build_instructions, build_user_input
from .schemas import AIRequest, AIResult, AIStreamEvent

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
except ImportError:
    OpenAI = None
    APIConnectionError = APIStatusError = APITimeoutError = RateLimitError = ()


class OpenAIResponsesProvider:
    """Private provider adapter owned exclusively by ``AIOrchestrator``."""

    def __init__(self, settings: Mapping | None = None) -> None:
        def read(name: str, default: object) -> object:
            if settings is not None:
                return settings.get(name, default)
            return os.getenv(name, str(default))

        self.api_key = str(read("OPENAI_API_KEY", "")).strip()
        self.model = str(read("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"
        self.fast_model = str(read("OPENAI_TUTOR_FAST_MODEL", self.model)).strip() or self.model
        self.tutor_model = str(read("OPENAI_TUTOR_MODEL", self.model)).strip() or self.model
        self.reasoning_model = str(
            read("OPENAI_TUTOR_REASONING_MODEL", self.tutor_model)
        ).strip() or self.tutor_model
        self.vision_model = str(read("OPENAI_VISION_MODEL", self.tutor_model)).strip() or self.tutor_model
        self.max_output_tokens = int(read("OPENAI_MAX_OUTPUT_TOKENS", 900))
        self.timeout = float(read("OPENAI_TIMEOUT_SECONDS", 45))
        self.max_retries = int(read("OPENAI_MAX_RETRIES", 1))
        store_responses = read("OPENAI_STORE_RESPONSES", False)
        self.store_responses = (
            store_responses
            if isinstance(store_responses, bool)
            else str(store_responses).strip() == "1"
        )
        self.client = (
            OpenAI(api_key=self.api_key, timeout=self.timeout, max_retries=self.max_retries)
            if self.api_key and OpenAI
            else None
        )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @staticmethod
    def _supports_reasoning_effort(model: str) -> bool:
        normalized = str(model or "").strip().lower()
        return normalized.startswith(("gpt-5", "o1", "o3", "o4"))

    @staticmethod
    def _supports_text_verbosity(model: str) -> bool:
        normalized = str(model or "").strip().lower()
        return normalized.startswith("gpt-5")

    @staticmethod
    def _reasoning_effort_for_model(model: str, requested: str) -> str:
        normalized = str(model or "").strip().lower()
        effort = str(requested or "low").strip().lower()
        if normalized.startswith(("o1", "o3", "o4")) and effort in {"none", "minimal"}:
            return "low"
        return effort

    def _model_for_request(self, request: AIRequest) -> str:
        if request.attachments or request.execution_plan.profile == "vision":
            return self.vision_model
        if request.execution_plan.profile == "fast":
            return self.fast_model
        if request.execution_plan.profile == "deep":
            return self.reasoning_model
        return self.tutor_model

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

        model = self._model_for_request(request)
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": build_instructions(
                request.context,
                question=request.question,
                history=request.history,
                has_images=bool(request.attachments),
                learner_memory=request.learner_memory,
                execution_plan=request.execution_plan,
            ),
            "input": input_items,
            "max_output_tokens": min(
                self.max_output_tokens,
                max(96, int(request.execution_plan.max_output_tokens or self.max_output_tokens)),
            ),
            "store": self.store_responses,
            "stream": stream,
            "metadata": {
                "app": "Mentory",
                "conversation_id": request.conversation_id[:64],
                "subject": request.context.subject[:32],
                "mode": getattr(request.context, "response_mode", "explain")[:16],
                "profile": request.execution_plan.profile[:16],
                "complexity": str(request.execution_plan.complexity_score),
            },
        }
        if self._supports_reasoning_effort(model):
            kwargs["reasoning"] = {
                "effort": self._reasoning_effort_for_model(
                    model,
                    request.execution_plan.reasoning_effort,
                )
            }
        if self._supports_text_verbosity(model):
            kwargs["text"] = {"verbosity": request.execution_plan.verbosity}
        return kwargs

    @staticmethod
    def _usage_dict(response: object) -> dict | None:
        usage_obj = getattr(response, "usage", None)
        return usage_obj.model_dump() if hasattr(usage_obj, "model_dump") else None

    @staticmethod
    def _failure(exc: Exception) -> tuple[str, str, bool]:
        if APITimeoutError and isinstance(exc, APITimeoutError):
            return "timeout", "The AI request timed out.", True
        if RateLimitError and isinstance(exc, RateLimitError):
            return "rate_limit", "The AI service rate limit was reached.", True
        if APIConnectionError and isinstance(exc, APIConnectionError):
            return "api_error", "The AI service could not be reached.", True
        if APIStatusError and isinstance(exc, APIStatusError):
            status_code = int(getattr(exc, "status_code", 0) or 0)
            return (
                "rate_limit" if status_code == 429 else "api_error",
                "The AI service rejected the request.",
                status_code == 429 or status_code >= 500,
            )
        return "api_error", "The AI service request failed.", False

    @staticmethod
    def _response_failure(response: object) -> tuple[str, str] | None:
        status = str(getattr(response, "status", "") or "").lower()
        if status not in {"failed", "cancelled", "incomplete"}:
            return None
        error = getattr(response, "error", None)
        code = str(getattr(error, "code", "") or status)
        return code, f"The AI response ended with status '{status}'."

    def complete_custom(
        self,
        *,
        instructions: str,
        text: str,
        attachments: tuple = (),
        model: str | None = None,
        max_output_tokens: int | None = None,
        metadata: dict[str, str] | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> AIResult:
        if not self.enabled:
            return AIResult("", "offline", "AI is not configured.", error_code="disabled")

        content = [{"type": "input_text", "text": text}]
        for attachment in attachments:
            if getattr(attachment, "kind", "") == "image":
                content.append({
                    "type": "input_image",
                    "image_url": image_to_data_url(attachment),
                    "detail": "auto",
                })

        kwargs: dict[str, Any] = {
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
        if response_format:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": str(response_format["name"])[:64],
                    "schema": dict(response_format["schema"]),
                    "strict": True,
                }
            }

        try:
            response = self.client.responses.create(**kwargs)
            response_failure = self._response_failure(response)
            if response_failure:
                code, message = response_failure
                return AIResult(
                    "",
                    "error",
                    message,
                    response_id=str(getattr(response, "id", "") or "") or None,
                    usage=self._usage_dict(response),
                    error_code="api_error",
                    retryable=code in {"server_error", "rate_limit_exceeded"},
                )
            output = str(getattr(response, "output_text", "") or "").strip()
            if not output:
                return AIResult(
                    "",
                    "error",
                    "The AI service returned an empty response.",
                    response_id=str(getattr(response, "id", "") or "") or None,
                    usage=self._usage_dict(response),
                    error_code="empty_response",
                    retryable=True,
                )
            return AIResult(
                text=output,
                mode="openai",
                response_id=str(getattr(response, "id", "") or "") or None,
                usage=self._usage_dict(response),
            )
        except Exception as exc:
            code, message, retryable = self._failure(exc)
            return AIResult("", "error", message, error_code=code, retryable=retryable)

    def complete(self, request: AIRequest) -> AIResult:
        if not self.enabled:
            return AIResult(
                request.fallback,
                "offline",
                "AI is not configured.",
                error_code="disabled",
            )
        try:
            response = self.client.responses.create(**self._request_kwargs(request))
            response_failure = self._response_failure(response)
            if response_failure:
                return AIResult(
                    request.fallback,
                    "offline",
                    response_failure[1],
                    response_id=str(getattr(response, "id", "") or "") or None,
                    usage=self._usage_dict(response),
                    error_code="api_error",
                    retryable=True,
                )
            text = str(getattr(response, "output_text", "") or "").strip()
            if not text:
                return AIResult(
                    request.fallback,
                    "offline",
                    "The AI service returned an empty response.",
                    response_id=str(getattr(response, "id", "") or "") or None,
                    usage=self._usage_dict(response),
                    error_code="empty_response",
                    retryable=True,
                )
            return AIResult(
                text=text,
                mode="openai",
                response_id=str(getattr(response, "id", "") or "") or None,
                usage=self._usage_dict(response),
            )
        except Exception as exc:
            code, message, retryable = self._failure(exc)
            return AIResult(
                request.fallback,
                "offline",
                message,
                error_code=code,
                retryable=retryable,
            )

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        if not self.enabled:
            yield AIStreamEvent("fallback", {
                "text": request.fallback,
                "mode": "offline",
                "error": "AI is not configured.",
                "error_code": "disabled",
                "retryable": False,
            })
            return

        response_id = None
        usage = None
        collected: list[str] = []
        pending_prefix = ""
        prefix_released = False
        try:
            stream = self.client.responses.create(**self._request_kwargs(request, stream=True))
            for event in stream:
                event_type = str(getattr(event, "type", "") or "")
                if event_type == "response.created":
                    response = getattr(event, "response", None)
                    response_id = str(getattr(response, "id", "") or "") or response_id
                elif event_type == "response.output_text.delta":
                    delta = str(getattr(event, "delta", "") or "")
                    if not delta:
                        continue
                    if not prefix_released:
                        pending_prefix += delta
                        ready = (
                            len(pending_prefix) >= 120
                            or "\n" in pending_prefix
                            or bool(re.search(r"[.!?…]\s", pending_prefix))
                        )
                        if not ready:
                            continue
                        cleaned = strip_generic_opening(pending_prefix)
                        prefix_released = True
                        pending_prefix = ""
                        if cleaned:
                            collected.append(cleaned)
                            yield AIStreamEvent("delta", {"text": cleaned})
                    else:
                        collected.append(delta)
                        yield AIStreamEvent("delta", {"text": delta})
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    response_id = str(getattr(response, "id", "") or "") or response_id
                    usage = self._usage_dict(response)
                elif event_type in {"error", "response.failed"}:
                    response = getattr(event, "response", None)
                    error = getattr(event, "error", None) or getattr(response, "error", None)
                    raise RuntimeError(str(getattr(error, "message", "") or "AI streaming error"))

            if pending_prefix:
                cleaned = strip_generic_opening(pending_prefix)
                if cleaned:
                    collected.append(cleaned)
                    yield AIStreamEvent("delta", {"text": cleaned})
            text = "".join(collected).strip()
            if not text:
                yield AIStreamEvent("fallback", {
                    "text": request.fallback,
                    "mode": "offline",
                    "error": "The AI service returned an empty response.",
                    "error_code": "empty_response",
                    "retryable": True,
                })
                return
            yield AIStreamEvent("completed", {
                "text": text,
                "mode": "openai",
                "response_id": response_id,
                "usage": usage,
            })
        except Exception as exc:
            code, message, retryable = self._failure(exc)
            partial = "".join(collected).strip()
            if partial:
                yield AIStreamEvent("completed", {
                    "text": partial,
                    "mode": "offline",
                    "response_id": response_id,
                    "usage": usage,
                    "error": message,
                    "error_code": code,
                    "retryable": retryable,
                })
            else:
                yield AIStreamEvent("fallback", {
                    "text": request.fallback,
                    "mode": "offline",
                    "error": message,
                    "error_code": code,
                    "retryable": retryable,
                })
