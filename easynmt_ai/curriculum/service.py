"""Application service for the curriculum generation lifecycle.

The service is the transaction boundary exposed to Flask.  It keeps provider
generation, deterministic validation, ownership checks, and SQLite lifecycle
transitions out of routes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Optional

from ..engines.curriculum import CurriculumEngine
from ..errors import AIError, AIErrorCode, EngineResult
from ..models import Curriculum, CurriculumStatus
from ..schemas import AIContext
from .policy import (
    CurriculumValidationResult,
    RegenerationDecision,
    RegenerationEvidence,
    should_regenerate_curriculum as decide_curriculum_regeneration,
    validate_curriculum,
)
from .repository import CurriculumRepository, CurriculumStateError
from .taxonomy import MathTaxonomy, load_math_taxonomy

if TYPE_CHECKING:
    from easynmt_core.progress import CurriculumProgressService


@dataclass(frozen=True)
class CurriculumValidationOutcome:
    """Persisted curriculum state paired with its deterministic validation."""

    curriculum: Curriculum
    validation: CurriculumValidationResult


class CurriculumService:
    """Coordinate owner-scoped curriculum generation and publication.

    Draft creation is idempotent for the complete generation identity.  A
    curriculum can only become active after local validation, and publication
    atomically supersedes the previous active version.
    """

    def __init__(
        self,
        engine: CurriculumEngine,
        repository: CurriculumRepository,
        *,
        progress_service: "CurriculumProgressService",
        taxonomy: Optional[MathTaxonomy] = None,
    ) -> None:
        self.engine = engine
        self.repository = repository
        self.progress_service = progress_service
        self.taxonomy = taxonomy or engine.taxonomy or load_math_taxonomy()

    @staticmethod
    def _error(
        code: AIErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> EngineResult:
        return EngineResult(error=AIError(code, message, retryable=retryable))

    def generate_curriculum_draft(
        self,
        context: AIContext,
        *,
        generation_reason: str = "manual_request",
        allow_fallback: bool = True,
        force_refresh: bool = False,
    ) -> EngineResult[Curriculum]:
        """Generate and persist an idempotent owner-scoped draft."""

        if context.subject != self.taxonomy.subject:
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "A curriculum is not available for this subject.",
            )
        active = self.repository.get_active(context.user_id, context.subject)
        effective_context = replace(
            context,
            active_curriculum_id=active.id if active else None,
        )
        try:
            _, request_fingerprint, _ = self.engine.generation_identity(
                effective_context,
                generation_reason=generation_reason,
            )
        except (TypeError, ValueError):
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "The curriculum generation request is invalid.",
            )

        existing = self.repository.find_by_request_fingerprint(
            effective_context.user_id,
            effective_context.subject,
            request_fingerprint,
        )
        if existing is not None:
            return EngineResult(value=existing, cached=True)

        generated = self.engine.generate(
            effective_context,
            generation_reason=generation_reason,
            active_curriculum=active,
            allow_fallback=allow_fallback,
            force_refresh=force_refresh,
        )
        if not generated.success:
            return generated
        try:
            stored = self.repository.create_draft(generated.value)
        except (CurriculumStateError, TypeError, ValueError):
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "The generated curriculum could not be persisted.",
            )
        except sqlite3.Error:
            return self._error(
                AIErrorCode.INTERNAL_ERROR,
                "Curriculum persistence is temporarily unavailable.",
                retryable=True,
            )
        return replace(generated, value=stored)

    def generate_baseline_curriculum_draft(
        self,
        context: AIContext,
        *,
        generation_reason: str = "manual_request",
    ) -> EngineResult[Curriculum]:
        """Persist an idempotent deterministic draft without provider access."""

        if context.subject != self.taxonomy.subject:
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "A curriculum is not available for this subject.",
            )
        try:
            baseline = self.engine.deterministic_baseline(
                context,
                generation_reason=generation_reason,
            )
        except (TypeError, ValueError):
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "The baseline curriculum request is invalid.",
            )
        existing = self.repository.find_by_request_fingerprint(
            context.user_id,
            context.subject,
            baseline.generation_metadata.request_fingerprint,
        )
        if existing is not None:
            return EngineResult(value=existing, cached=True)
        try:
            stored = self.repository.create_draft(baseline)
        except (CurriculumStateError, TypeError, ValueError):
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "The baseline curriculum could not be persisted.",
            )
        except sqlite3.Error:
            return self._error(
                AIErrorCode.INTERNAL_ERROR,
                "Curriculum persistence is temporarily unavailable.",
                retryable=True,
            )
        return EngineResult(value=stored, fallback_used=True)

    def validate_curriculum(
        self,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> EngineResult[CurriculumValidationOutcome]:
        """Validate a draft locally and persist validated/rejected state."""

        curriculum = self.repository.get_curriculum(user_id, curriculum_id)
        if curriculum is None:
            return self._error(AIErrorCode.VALIDATION_ERROR, "Curriculum not found.")
        if curriculum.status not in {
            CurriculumStatus.DRAFT,
            CurriculumStatus.VALIDATED,
        }:
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                f"A {curriculum.status.value} curriculum cannot be validated.",
            )
        validation = validate_curriculum(curriculum, self.taxonomy)
        try:
            stored = self.repository.save_validation(
                user_id=user_id,
                curriculum_id=curriculum_id,
                validation_result=validation.to_dict(),
            )
        except (KeyError, CurriculumStateError, TypeError, ValueError):
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "The curriculum validation state changed before it could be saved.",
            )
        except sqlite3.Error:
            return self._error(
                AIErrorCode.INTERNAL_ERROR,
                "Curriculum validation could not be saved.",
                retryable=True,
            )
        if not validation.valid:
            return EngineResult(
                value=CurriculumValidationOutcome(stored, validation),
                error=AIError(
                    AIErrorCode.VALIDATION_ERROR,
                    "Curriculum failed deterministic validation.",
                    details={"issue_codes": [issue.code for issue in validation.issues]},
                ),
            )
        return EngineResult(value=CurriculumValidationOutcome(stored, validation))

    def publish_curriculum(
        self,
        *,
        user_id: int,
        curriculum_id: str,
    ) -> EngineResult[Curriculum]:
        """Validate then atomically publish a curriculum for its owner."""

        curriculum = self.repository.get_curriculum(user_id, curriculum_id)
        if curriculum is None:
            return self._error(AIErrorCode.VALIDATION_ERROR, "Curriculum not found.")
        if curriculum.status is CurriculumStatus.PUBLISHED:
            try:
                published = self.repository.publish(
                    user_id=user_id,
                    curriculum_id=curriculum_id,
                    progress_initializer=self.progress_service.initialize_for_publication,
                )
            except sqlite3.Error:
                return self._error(
                    AIErrorCode.INTERNAL_ERROR,
                    "Published curriculum progress could not be initialized.",
                    retryable=True,
                )
            return EngineResult(value=published)
        if curriculum.status is CurriculumStatus.DRAFT:
            validated = self.validate_curriculum(
                user_id=user_id,
                curriculum_id=curriculum_id,
            )
            if not validated.success:
                return EngineResult(error=validated.error)
            curriculum = validated.value.curriculum
        if curriculum.status is not CurriculumStatus.VALIDATED:
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                f"A {curriculum.status.value} curriculum cannot be published.",
            )

        # Revalidate immediately before publication so a taxonomy change cannot
        # activate a stale or structurally invalid draft.
        validation = validate_curriculum(curriculum, self.taxonomy)
        if not validation.valid:
            try:
                self.repository.save_validation(
                    user_id=user_id,
                    curriculum_id=curriculum_id,
                    validation_result=validation.to_dict(),
                )
            except sqlite3.Error:
                return self._error(
                    AIErrorCode.INTERNAL_ERROR,
                    "The rejected curriculum state could not be saved.",
                    retryable=True,
                )
            except (KeyError, CurriculumStateError):
                return self._error(
                    AIErrorCode.VALIDATION_ERROR,
                    "The curriculum state changed before publication.",
                )
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "Curriculum no longer satisfies the current taxonomy.",
            )
        try:
            published = self.repository.publish(
                user_id=user_id,
                curriculum_id=curriculum_id,
                progress_initializer=self.progress_service.initialize_for_publication,
            )
        except (KeyError, CurriculumStateError):
            return self._error(
                AIErrorCode.VALIDATION_ERROR,
                "The curriculum could not be published from its current state.",
            )
        except sqlite3.Error:
            return self._error(
                AIErrorCode.INTERNAL_ERROR,
                "Curriculum publication is temporarily unavailable.",
                retryable=True,
            )
        return EngineResult(value=published)

    def get_active_curriculum(self, *, user_id: int, subject: str) -> Optional[Curriculum]:
        """Return the owner's active curriculum, if one exists."""

        return self.repository.get_active(user_id, subject)

    def get_curriculum_history(self, *, user_id: int, subject: str) -> list[Curriculum]:
        """Return immutable versions newest first for audit and future rollback."""

        return self.repository.get_history(user_id, subject)

    def should_regenerate_curriculum(
        self,
        *,
        user_id: int,
        subject: str,
        evidence: RegenerationEvidence,
    ) -> RegenerationDecision:
        """Evaluate explicit regeneration thresholds without mutating state."""

        active = self.repository.get_active(user_id, subject)
        return decide_curriculum_regeneration(active, self.taxonomy, evidence)

    def regeneration_decision(
        self,
        *,
        user_id: int,
        subject: str,
        evidence: RegenerationEvidence,
    ) -> RegenerationDecision:
        """Compatibility alias for ``should_regenerate_curriculum``."""

        return self.should_regenerate_curriculum(
            user_id=user_id,
            subject=subject,
            evidence=evidence,
        )
