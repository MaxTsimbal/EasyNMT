"""Production mathematics curriculum domain."""

from .policy import (
    CurriculumPolicy,
    CurriculumValidationIssue,
    CurriculumValidationResult,
    RegenerationDecision,
    RegenerationEvidence,
    build_curriculum_policy,
    should_regenerate_curriculum,
    validate_curriculum,
)
from .repository import CurriculumRepository, CurriculumStateError
from .service import CurriculumService, CurriculumValidationOutcome
from .taxonomy import (
    LEGACY_MATH_LESSON_TOPIC_MAP,
    MathTaxonomy,
    TaxonomyTopic,
    TaxonomyValidationError,
    TaxonomyValidationIssue,
    TaxonomyValidationResult,
    load_math_taxonomy,
    validate_taxonomy_payload,
)

__all__ = [
    "CurriculumPolicy",
    "CurriculumRepository",
    "CurriculumService",
    "CurriculumStateError",
    "CurriculumValidationIssue",
    "CurriculumValidationOutcome",
    "CurriculumValidationResult",
    "LEGACY_MATH_LESSON_TOPIC_MAP",
    "MathTaxonomy",
    "TaxonomyTopic",
    "TaxonomyValidationError",
    "TaxonomyValidationIssue",
    "TaxonomyValidationResult",
    "RegenerationDecision",
    "RegenerationEvidence",
    "build_curriculum_policy",
    "load_math_taxonomy",
    "should_regenerate_curriculum",
    "validate_curriculum",
    "validate_taxonomy_payload",
]
