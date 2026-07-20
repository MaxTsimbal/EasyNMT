"""Typed, provider-neutral curriculum progress failures."""
from __future__ import annotations


class CurriculumProgressError(Exception):
    """Base error safe to translate into an API response."""

    code = "curriculum_progress_error"
    http_status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CurriculumProgressNotFound(CurriculumProgressError):
    code = "curriculum_progress_not_found"
    http_status = 404


class CurriculumUnitNotFound(CurriculumProgressError):
    code = "curriculum_unit_not_found"
    http_status = 404


class CurriculumOwnershipError(CurriculumProgressError):
    code = "curriculum_ownership_error"
    http_status = 403


class CurriculumNotActive(CurriculumProgressError):
    code = "curriculum_not_active"
    http_status = 409


class CurriculumSuperseded(CurriculumNotActive):
    code = "curriculum_superseded"


class InvalidProgressTransition(CurriculumProgressError):
    code = "invalid_progress_transition"
    http_status = 409


class PrerequisitesNotSatisfied(CurriculumProgressError):
    code = "prerequisites_not_satisfied"
    http_status = 409


class AssessmentEvidenceInvalid(CurriculumProgressError):
    code = "assessment_evidence_invalid"
    http_status = 400


class ProgressConflict(CurriculumProgressError):
    code = "progress_conflict"
    http_status = 409


class ProgressInitializationError(CurriculumProgressError):
    code = "progress_initialization_error"
    http_status = 409
