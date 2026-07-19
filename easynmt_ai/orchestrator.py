"""Central orchestration boundary for every EasyNMT AI request."""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Callable, Iterator, Mapping, Optional, TypeVar

from .cache import AICache, NullAICache
from .errors import AIError, AIErrorCode, EngineResult
from .models import AIModelValidationError
from .prompts import PromptSpec
from .repository import AIRepository
from .schemas import AIContext, AIRequest, AIResult, AIStreamEvent
from .service import OpenAIResponsesProvider


T = TypeVar("T")


class AIOrchestrator:
    """The only public component permitted to execute OpenAI requests.

    Routes and engines submit provider-neutral values here. The orchestrator
    owns the private OpenAI adapter, telemetry, structured-output parsing,
    caching hooks, and graceful provider failure handling.
    """

    def __init__(
        self,
        settings: Mapping | None = None,
        repository: AIRepository | None = None,
        *,
        cache: AICache | None = None,
        logger: logging.Logger | None = None,
        _gateway: OpenAIResponsesProvider | None = None,
    ) -> None:
        self._gateway = _gateway or OpenAIResponsesProvider(settings)
        self.repository = repository
        self.cache = cache or NullAICache()
        self.logger = logger or logging.getLogger("easynmt.ai")

    @property
    def enabled(self) -> bool:
        return self._gateway.enabled

    @property
    def model_identifier(self) -> str:
        """Return the configured text model without exposing the provider adapter."""

        return str(getattr(self._gateway, "model", "unknown") or "unknown")

    @staticmethod
    def clean_text(value: object) -> str:
        text = str(value or "").strip()
        return re.sub(r"^\s*(?:Easy|Ізі)\s*:\s*", "", text, flags=re.IGNORECASE).strip()

    @staticmethod
    def new_message_id(prefix: str = "msg") -> str:
        return f"{prefix}-{uuid.uuid4()}"

    @staticmethod
    def _total_tokens(usage: Optional[Mapping[str, Any]]) -> Optional[int]:
        if not usage:
            return None
        value = usage.get("total_tokens")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _log_request(
        self,
        *,
        engine_name: str,
        user_id: int,
        started_at: float,
        success: bool,
        usage: Optional[Mapping[str, Any]] = None,
        error_code: Optional[str] = None,
        response_id: Optional[str] = None,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        self.logger.info(
            "AI request engine=%s user_id=%s success=%s execution_ms=%s tokens=%s error_code=%s",
            engine_name,
            user_id,
            success,
            elapsed_ms,
            self._total_tokens(usage),
            error_code or "none",
            extra={
                "ai_engine": engine_name,
                "ai_execution_ms": elapsed_ms,
                "ai_token_usage": self._total_tokens(usage),
                "ai_success": success,
                "ai_user_id": user_id,
                "ai_error_code": error_code,
                "ai_response_id": response_id,
            },
        )

    @staticmethod
    def _unexpected_failure(exc: Exception, fallback: str = "") -> AIResult:
        if isinstance(exc, TimeoutError):
            return AIResult(
                fallback,
                "offline",
                "The AI request timed out.",
                error_code=AIErrorCode.TIMEOUT.value,
                retryable=True,
            )
        return AIResult(
            fallback,
            "offline",
            "The AI request failed safely.",
            error_code=AIErrorCode.INTERNAL_ERROR.value,
        )

    def _call(
        self,
        operation: Callable[[], AIResult],
        *,
        engine_name: str,
        user_id: int,
        fallback: str = "",
        log_result: bool = True,
    ) -> AIResult:
        started_at = time.perf_counter()
        try:
            result = operation()
        except Exception as exc:
            result = self._unexpected_failure(exc, fallback)
            self.logger.exception(
                "Unexpected AI adapter failure engine=%s user_id=%s",
                engine_name,
                user_id,
            )
        if log_result:
            self._log_request(
                engine_name=engine_name,
                user_id=user_id,
                started_at=started_at,
                success=result.mode == "openai" and not result.error_code,
                usage=result.usage,
                error_code=result.error_code,
                response_id=result.response_id,
            )
        return result

    def prepare(self, request: AIRequest) -> None:
        """Persist a tutor request before contacting the provider."""

        if self.repository is None:
            return
        title = request.question.strip().replace("\n", " ")[:46]
        if len(request.question.strip()) > 46:
            title = f"{title.rstrip()}…"
        self.repository.upsert_conversation(
            user_id=request.context.user_id,
            conversation_id=request.conversation_id,
            title=title or "Нова розмова",
            subject=request.context.subject,
            lesson_id=request.context.current_lesson,
            response_mode=getattr(request.context, "response_mode", "explain"),
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

    def complete_stateless(self, request: AIRequest, *, engine_name: str) -> AIResult:
        """Execute an existing text workflow without conversation persistence."""

        return self._call(
            lambda: self._gateway.complete(request),
            engine_name=engine_name,
            user_id=request.context.user_id,
            fallback=request.fallback,
        )

    def complete(self, request: AIRequest) -> AIResult:
        """Execute and persist the existing tutor conversation workflow."""

        self.prepare(request)
        result = self.complete_stateless(request, engine_name="tutor")
        result.text = self.clean_text(result.text)
        if self.repository is not None:
            self.repository.add_message(
                message_id=request.assistant_message_id,
                conversation_id=request.conversation_id,
                user_id=request.context.user_id,
                role="assistant",
                content=result.text,
                provider_mode=result.mode,
                response_id=result.response_id,
                metadata={
                    "usage": result.usage or {},
                    "error_code": result.error_code,
                    "retryable": result.retryable,
                },
            )
        return result

    def complete_prompt(
        self,
        *,
        engine_name: str,
        context: AIContext,
        prompt: PromptSpec,
        attachments: tuple = (),
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> AIResult:
        """Execute a specialized prompt through the central boundary."""

        token_limit = max_output_tokens or context.available_tokens
        return self._call(
            lambda: self._gateway.complete_custom(
                instructions=prompt.instructions,
                text=prompt.user_input,
                attachments=attachments,
                model=model,
                max_output_tokens=token_limit,
                metadata={
                    "app": "EasyNMT",
                    "engine": engine_name,
                    "user_id": str(context.user_id),
                },
                response_format={"name": prompt.schema_name, "schema": prompt.schema},
            ),
            engine_name=engine_name,
            user_id=context.user_id,
        )

    @staticmethod
    def _decode_json(text: str) -> Mapping[str, Any]:
        candidate = str(text or "").strip()
        if candidate.startswith("```") and candidate.endswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*```$", "", candidate)
        value = json.loads(candidate)
        if not isinstance(value, Mapping):
            raise ValueError("AI response root must be an object")
        return value

    @staticmethod
    def _error_from_result(result: AIResult) -> AIError:
        try:
            code = AIErrorCode(result.error_code or AIErrorCode.API_ERROR.value)
        except ValueError:
            code = AIErrorCode.API_ERROR
        return AIError(
            code=code,
            message=result.error or "The AI request failed.",
            retryable=result.retryable,
            request_id=result.response_id,
        )

    def execute_structured(
        self,
        *,
        engine_name: str,
        context: AIContext,
        prompt: PromptSpec,
        parser: Callable[[Mapping[str, Any]], T],
        attachments: tuple = (),
        cache_namespace: str | None = None,
        cache_key: str | None = None,
        cache_ttl_seconds: int | None = None,
        force_refresh: bool = False,
        max_output_tokens: int | None = None,
    ) -> EngineResult[T]:
        """Execute, validate, and optionally cache a typed engine response."""

        if cache_namespace and cache_key and not force_refresh:
            try:
                cached = self.cache.get(cache_namespace, cache_key)
                if cached is not None:
                    return EngineResult(value=parser(cached), cached=True)
            except (AIModelValidationError, TypeError, ValueError):
                self.logger.warning(
                    "Ignoring invalid AI cache entry namespace=%s key=%s",
                    cache_namespace,
                    cache_key,
                )
            except Exception:
                self.logger.exception(
                    "AI cache read failed namespace=%s key=%s",
                    cache_namespace,
                    cache_key,
                )

        started_at = time.perf_counter()
        result = self._call(
            lambda: self._gateway.complete_custom(
                instructions=prompt.instructions,
                text=prompt.user_input,
                attachments=attachments,
                max_output_tokens=max_output_tokens or context.available_tokens,
                metadata={
                    "app": "EasyNMT",
                    "engine": engine_name,
                    "user_id": str(context.user_id),
                },
                response_format={"name": prompt.schema_name, "schema": prompt.schema},
            ),
            engine_name=engine_name,
            user_id=context.user_id,
            log_result=False,
        )
        if result.mode != "openai" or result.error_code:
            error = self._error_from_result(result)
            self._log_request(
                engine_name=engine_name,
                user_id=context.user_id,
                started_at=started_at,
                success=False,
                usage=result.usage,
                error_code=error.code.value,
                response_id=result.response_id,
            )
            return EngineResult(error=error, usage=result.usage, response_id=result.response_id)

        try:
            payload = self._decode_json(result.text)
        except (json.JSONDecodeError, ValueError) as exc:
            error = AIError(
                code=AIErrorCode.INVALID_JSON,
                message="The AI service returned invalid structured data.",
                retryable=True,
                request_id=result.response_id,
                details={"reason": str(exc)[:160]},
            )
            self._log_request(
                engine_name=engine_name,
                user_id=context.user_id,
                started_at=started_at,
                success=False,
                usage=result.usage,
                error_code=error.code.value,
                response_id=result.response_id,
            )
            return EngineResult(error=error, usage=result.usage, response_id=result.response_id)

        try:
            value = parser(payload)
        except Exception as exc:
            error = AIError(
                code=AIErrorCode.VALIDATION_ERROR,
                message="The AI response did not match the engine contract.",
                retryable=True,
                request_id=result.response_id,
                details={"reason": str(exc)[:160]},
            )
            self._log_request(
                engine_name=engine_name,
                user_id=context.user_id,
                started_at=started_at,
                success=False,
                usage=result.usage,
                error_code=error.code.value,
                response_id=result.response_id,
            )
            return EngineResult(error=error, usage=result.usage, response_id=result.response_id)

        if cache_namespace and cache_key:
            try:
                serialized = value.to_dict() if hasattr(value, "to_dict") else dict(payload)
                self.cache.set(
                    cache_namespace,
                    cache_key,
                    serialized,
                    ttl_seconds=cache_ttl_seconds,
                )
            except Exception:
                self.logger.exception(
                    "AI cache write failed namespace=%s key=%s",
                    cache_namespace,
                    cache_key,
                )

        self._log_request(
            engine_name=engine_name,
            user_id=context.user_id,
            started_at=started_at,
            success=True,
            usage=result.usage,
            response_id=result.response_id,
        )
        return EngineResult(
            value=value,
            usage=result.usage,
            response_id=result.response_id,
        )

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        """Stream the tutor response while persisting one final assistant row."""

        self.prepare(request)
        started_at = time.perf_counter()
        final_text = ""
        final_mode = "offline"
        response_id = None
        usage = None
        fallback_error = None
        error_code = None
        retryable = False

        try:
            events = self._gateway.stream(request)
            for event in events:
                if event.type == "delta":
                    final_text += str(event.data.get("text", ""))
                    yield event
                elif event.type == "completed":
                    final_text = str(event.data.get("text", final_text))
                    final_mode = str(event.data.get("mode", "openai"))
                    response_id = event.data.get("response_id")
                    usage = event.data.get("usage")
                    fallback_error = event.data.get("error")
                    error_code = event.data.get("error_code")
                    retryable = bool(event.data.get("retryable", False))
                elif event.type == "fallback":
                    fallback_text = self.clean_text(event.data.get("text", request.fallback))
                    fallback_error = event.data.get("error")
                    error_code = event.data.get("error_code")
                    retryable = bool(event.data.get("retryable", False))
                    final_text = fallback_text
                    final_mode = "offline"
                    yield AIStreamEvent("fallback", {
                        "text": fallback_text,
                        "error": fallback_error,
                        "error_code": error_code,
                        "retryable": retryable,
                    })
        except Exception as exc:
            failure = self._unexpected_failure(exc, request.fallback)
            final_text = failure.text
            fallback_error = failure.error
            error_code = failure.error_code
            retryable = failure.retryable
            self.logger.exception(
                "Unexpected AI stream failure engine=tutor user_id=%s",
                request.context.user_id,
            )

        final_text = self.clean_text(final_text or request.fallback)
        if self.repository is not None:
            self.repository.add_message(
                message_id=request.assistant_message_id,
                conversation_id=request.conversation_id,
                user_id=request.context.user_id,
                role="assistant",
                content=final_text,
                provider_mode=final_mode,
                response_id=response_id,
                metadata={
                    "usage": usage or {},
                    "fallback_error": fallback_error,
                    "error_code": error_code,
                    "retryable": retryable,
                },
            )
        self._log_request(
            engine_name="tutor",
            user_id=request.context.user_id,
            started_at=started_at,
            success=final_mode == "openai" and not error_code,
            usage=usage,
            error_code=error_code,
            response_id=response_id,
        )
        yield AIStreamEvent("done", {
            "text": final_text,
            "mode": final_mode,
            "response_id": response_id,
            "usage": usage,
            "error": fallback_error,
            "error_code": error_code,
            "retryable": retryable,
            "message_id": request.assistant_message_id,
        })
