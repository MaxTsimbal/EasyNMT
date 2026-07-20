import copy
import json
import logging
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from easynmt_ai import AIContext, AIErrorCode, AIOrchestrator, AIResult, CurriculumEngine
from easynmt_ai.curriculum import (
    CurriculumRepository,
    CurriculumService,
    RegenerationEvidence,
    build_curriculum_policy,
    load_math_taxonomy,
    should_regenerate_curriculum,
    validate_curriculum,
    validate_taxonomy_payload,
)
from easynmt_ai.curriculum.policy import (
    curriculum_context_fingerprint,
    curriculum_request_fingerprint,
)
from easynmt_ai.curriculum.taxonomy import MATH_TAXONOMY_FILE
from easynmt_ai.models import CurriculumStatus
from easynmt_ai.prompts.curriculum import build_curriculum_prompt
from easynmt_core.progress import CurriculumProgressRepository, CurriculumProgressService


class FakeGateway:
    def __init__(self, *responses, model="test-model"):
        self.enabled = True
        self.model = model
        self.responses = list(responses)
        self.calls = []

    def complete_custom(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, namespace, key):
        return self.values.get((namespace, key))

    def set(self, namespace, key, value, *, ttl_seconds=None):
        self.values[(namespace, key)] = dict(value)


def ai_response(payload):
    return AIResult(
        json.dumps(payload),
        "openai",
        response_id="resp-curriculum-test",
        usage={"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
    )


def provider_failure(code="disabled"):
    return AIResult(
        "",
        "offline",
        "provider unavailable",
        error_code=code,
        retryable=code in {"timeout", "rate_limit"},
    )


def math_context(user_id=1, **changes):
    values = {
        "user_id": user_id,
        "subject": "math",
        "goal_score": 170,
        "difficulty": "adaptive",
        "diagnostic_score": 12,
        "diagnostic_total": 20,
        "study_minutes_per_week": 300,
    }
    values.update(changes)
    return AIContext(**values)


def canonical_payload():
    with MATH_TAXONOMY_FILE.open("r", encoding="utf-8") as source:
        return json.load(source)


def issue_codes(result):
    return {issue.code for issue in result.issues}


class TaxonomyValidationTests(unittest.TestCase):
    def test_canonical_taxonomy_covers_required_domains_and_is_orderable(self):
        taxonomy = load_math_taxonomy()
        domains = {topic.domain for topic in taxonomy.topics}
        self.assertEqual(len(taxonomy.topics), 39)
        self.assertTrue({
            "numbers_expressions",
            "fractions_percentages_proportions",
            "algebraic_expressions",
            "equations_inequalities",
            "functions_graphs",
            "sequences_progressions",
            "geometry",
            "coordinate_geometry",
            "trigonometry",
            "probability",
            "statistics",
            "combinatorics",
            "applied_word_problems",
        }.issubset(domains))
        ordered = taxonomy.topological_order()
        self.assertEqual(len(ordered), len(taxonomy.topics))
        positions = {topic_id: index for index, topic_id in enumerate(ordered)}
        for topic in taxonomy.topics:
            for dependency in (
                *topic.prerequisite_topic_ids,
                *topic.recommended_after_topic_ids,
            ):
                self.assertLess(positions[dependency], positions[topic.id])

    def test_rejects_missing_fields_duplicates_and_unknown_dependencies(self):
        cases = []

        missing = canonical_payload()
        del missing["topics"][0]["title_uk"]
        cases.append((missing, "missing_field"))

        duplicate_id = canonical_payload()
        duplicate_id["topics"][1]["id"] = duplicate_id["topics"][0]["id"]
        cases.append((duplicate_id, "duplicate_topic_id"))

        duplicate_slug = canonical_payload()
        duplicate_slug["topics"][1]["slug"] = duplicate_slug["topics"][0]["slug"]
        cases.append((duplicate_slug, "duplicate_slug"))

        unknown = canonical_payload()
        unknown["topics"][0]["prerequisite_topic_ids"] = ["math.unknown.topic"]
        cases.append((unknown, "unknown_prerequisite"))

        self_dependency = canonical_payload()
        topic_id = self_dependency["topics"][0]["id"]
        self_dependency["topics"][0]["prerequisite_topic_ids"] = [topic_id]
        cases.append((self_dependency, "self_dependency"))

        for payload, expected in cases:
            with self.subTest(expected=expected):
                result = validate_taxonomy_payload(payload)
                self.assertFalse(result.valid)
                self.assertIn(expected, issue_codes(result))

    def test_rejects_prerequisite_and_recommended_order_cycles(self):
        prerequisite_cycle = canonical_payload()
        first = prerequisite_cycle["topics"][0]
        second = prerequisite_cycle["topics"][1]
        first["prerequisite_topic_ids"] = [second["id"]]
        second["prerequisite_topic_ids"] = [first["id"]]
        result = validate_taxonomy_payload(prerequisite_cycle)
        self.assertIn("circular_dependency", issue_codes(result))

        ordering_cycle = canonical_payload()
        first = ordering_cycle["topics"][0]
        second = ordering_cycle["topics"][1]
        first["recommended_after_topic_ids"] = [second["id"]]
        second["prerequisite_topic_ids"] = [first["id"]]
        result = validate_taxonomy_payload(ordering_cycle)
        self.assertIn("impossible_ordering", issue_codes(result))


class CurriculumGenerationTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = load_math_taxonomy()
        self.context = math_context()
        self.logger = logging.getLogger("tests.curriculum")
        self.logger.handlers = [logging.NullHandler()]
        self.logger.propagate = False

    def valid_proposal(self, context=None):
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=FakeGateway(provider_failure()), logger=self.logger),
            taxonomy=self.taxonomy,
        )
        _, _, policy = engine.generation_identity(
            context or self.context,
            generation_reason="manual_request",
        )
        return engine._deterministic_payload(policy)

    def generate_provider_payload(self, payload, *, allow_fallback=False, context=None):
        gateway = FakeGateway(ai_response(payload))
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=gateway, logger=self.logger),
            taxonomy=self.taxonomy,
        )
        return engine.generate(
            context or self.context,
            allow_fallback=allow_fallback,
        ), gateway

    def test_valid_provider_proposal_is_wrapped_with_authoritative_metadata(self):
        result, gateway = self.generate_provider_payload(self.valid_proposal())
        self.assertTrue(result.success)
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.value.status, CurriculumStatus.DRAFT)
        self.assertEqual(result.value.user_id, self.context.user_id)
        self.assertEqual(result.value.taxonomy_version, self.taxonomy.version)
        self.assertEqual(result.value.generation_metadata.source, "openai")
        self.assertEqual(result.value.generation_metadata.total_tokens, 300)
        self.assertTrue(validate_curriculum(result.value, self.taxonomy).valid)
        self.assertEqual(gateway.calls[0]["max_output_tokens"], 5000)

    def test_unknown_duplicate_empty_and_malformed_ai_units_are_rejected(self):
        valid = self.valid_proposal()
        cases = []

        unknown = copy.deepcopy(valid)
        unknown["units"][0]["topic_id"] = "math.invented.topic"
        cases.append(unknown)

        duplicate = copy.deepcopy(valid)
        duplicate["units"][1]["topic_id"] = duplicate["units"][0]["topic_id"]
        cases.append(duplicate)

        empty = copy.deepcopy(valid)
        empty["units"] = []
        cases.append(empty)

        priority = copy.deepcopy(valid)
        priority["units"][0]["priority"] = "urgent-ish"
        cases.append(priority)

        duration = copy.deepcopy(valid)
        duration["units"][0]["estimated_duration_minutes"] = 1
        cases.append(duration)

        for payload in cases:
            with self.subTest(payload=payload["units"][:1]):
                result, _ = self.generate_provider_payload(payload)
                self.assertFalse(result.success)
                self.assertEqual(result.error.code, AIErrorCode.VALIDATION_ERROR)

    def test_invalid_prerequisite_order_is_rejected(self):
        payload = self.valid_proposal()
        payload["units"].reverse()
        result, _ = self.generate_provider_payload(payload)
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, AIErrorCode.VALIDATION_ERROR)

    def test_timeout_and_invalid_json_return_safe_fallback_drafts(self):
        failures = [TimeoutError("slow"), AIResult("not json", "openai")]
        expected = [AIErrorCode.TIMEOUT, AIErrorCode.INVALID_JSON]
        for provider_result, expected_code in zip(failures, expected):
            with self.subTest(expected_code=expected_code):
                gateway = FakeGateway(provider_result)
                engine = CurriculumEngine(
                    AIOrchestrator(_gateway=gateway, logger=self.logger),
                    taxonomy=self.taxonomy,
                )
                result = engine.generate(self.context)
                self.assertTrue(result.success)
                self.assertTrue(result.fallback_used)
                self.assertEqual(result.value.generation_metadata.source, "deterministic")
                self.assertEqual(result.warnings[0].code, expected_code)
                self.assertEqual(
                    result.value.generation_metadata.fallback_error_code,
                    expected_code.value,
                )
                self.assertTrue(validate_curriculum(result.value, self.taxonomy).valid)

    def test_provider_failure_can_be_returned_without_fallback(self):
        gateway = FakeGateway(provider_failure("rate_limit"))
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=gateway, logger=self.logger),
            taxonomy=self.taxonomy,
        )
        result = engine.generate(self.context, allow_fallback=False)
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, AIErrorCode.RATE_LIMIT)

    def test_missing_optional_context_fields_do_not_break_fallback(self):
        context = AIContext(user_id=1, subject="math")
        gateway = FakeGateway(provider_failure())
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=gateway, logger=self.logger),
            taxonomy=self.taxonomy,
        )
        result = engine.generate(context)
        self.assertTrue(result.success)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.value.target_score, 170)

    def test_cache_reuses_validated_curriculum_and_key_is_fully_versioned(self):
        payload = self.valid_proposal()
        gateway = FakeGateway(ai_response(payload))
        cache = MemoryCache()
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=gateway, cache=cache, logger=self.logger),
            taxonomy=self.taxonomy,
        )
        first = engine.generate(self.context)
        second = engine.generate(self.context)
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertTrue(second.cached)
        self.assertEqual(first.value.id, second.value.id)
        self.assertEqual(len(gateway.calls), 1)

        base = {
            "context_fingerprint": "context",
            "taxonomy_version": "tax-v1",
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "model_identifier": "model-v1",
            "generation_reason": "manual_request",
        }
        fingerprints = {curriculum_request_fingerprint(**base)}
        for field in base:
            changed = dict(base)
            changed[field] = f"{base[field]}-changed"
            fingerprints.add(curriculum_request_fingerprint(**changed))
        self.assertEqual(len(fingerprints), len(base) + 1)

    def test_prompt_excludes_identifiers_and_raw_mistakes(self):
        context = math_context(
            user_id=987654,
            known_weaknesses=("fractions",),
            recent_mistakes=("SECRET RAW ANSWER about fractions",),
            metadata={"email": "learner@example.com", "oauth": "secret"},
        )
        policy = build_curriculum_policy(context, self.taxonomy)
        prompt = build_curriculum_prompt(
            context,
            taxonomy=self.taxonomy,
            policy=policy,
            generation_reason="manual_request",
        )
        self.assertNotIn("987654", prompt.user_input)
        self.assertNotIn("SECRET RAW ANSWER", prompt.user_input)
        self.assertNotIn("learner@example.com", prompt.user_input)
        self.assertNotIn("oauth", prompt.user_input)
        self.assertIn("math.numbers.fractions", prompt.user_input)

    def test_recent_mistakes_affect_policy_without_entering_context_fingerprint_raw(self):
        context = math_context(recent_mistakes=("Repeated fraction calculation error",))
        policy = build_curriculum_policy(context, self.taxonomy)
        self.assertIn("math.numbers.fractions", policy.weakness_topic_ids)
        fingerprint = curriculum_context_fingerprint(context, self.taxonomy)
        self.assertEqual(len(fingerprint), 64)


class GoldenCurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = load_math_taxonomy()

    def generate(self, context):
        logger = logging.getLogger(f"tests.curriculum.golden.{context.user_id}")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=FakeGateway(provider_failure()), logger=logger),
            taxonomy=self.taxonomy,
        )
        result = engine.generate(context)
        self.assertTrue(result.success)
        self.assertTrue(result.fallback_used)
        self.assertTrue(validate_curriculum(result.value, self.taxonomy).valid)
        self.assertEqual(
            [unit.order for unit in result.value.units],
            list(range(1, len(result.value.units) + 1)),
        )
        self.assertEqual(
            result.value.review_checkpoints[-1].after_unit_order,
            len(result.value.units),
        )
        return result.value

    def test_beginner_modest_score(self):
        curriculum = self.generate(math_context(
            11,
            goal_score=150,
            difficulty="beginner",
            diagnostic_score=3,
            diagnostic_total=20,
        ))
        self.assertEqual(curriculum.starting_level, "beginner")
        self.assertEqual({unit.difficulty for unit in curriculum.units}, {"foundation"})
        self.assertTrue(all(unit.mastery_target == 0.75 for unit in curriculum.units))

    def test_average_learner_targeting_170(self):
        curriculum = self.generate(math_context(12, goal_score=170))
        self.assertEqual(curriculum.starting_level, "average")
        self.assertIn("intermediate", {unit.difficulty for unit in curriculum.units})
        self.assertNotIn("advanced", {unit.difficulty for unit in curriculum.units})

    def test_strong_learner_targeting_190(self):
        curriculum = self.generate(math_context(
            13,
            goal_score=190,
            difficulty="strong",
            diagnostic_score=18,
            diagnostic_total=20,
        ))
        self.assertEqual(curriculum.starting_level, "strong")
        self.assertIn("advanced", {unit.difficulty for unit in curriculum.units})
        self.assertTrue(all(unit.mastery_target == 0.92 for unit in curriculum.units))

    def test_fraction_weakness_is_critical(self):
        curriculum = self.generate(math_context(14, known_weaknesses=("fractions",)))
        unit = next(item for item in curriculum.units if item.topic_id == "math.numbers.fractions")
        self.assertEqual(unit.priority, "critical")
        self.assertEqual(unit.reason_code, "known_weakness")

    def test_geometry_weakness_is_critical(self):
        curriculum = self.generate(math_context(15, known_weaknesses=("geometry",)))
        unit = next(
            item for item in curriculum.units
            if item.topic_id == "math.geometry.triangles_angles"
        )
        self.assertEqual(unit.priority, "critical")

    def test_mastered_early_algebra_is_omitted(self):
        mastered = {
            "math.algebra.expressions_polynomials": 1.0,
            "math.algebra.factorization": 1.0,
            "math.algebra.linear_equations": 1.0,
        }
        curriculum = self.generate(math_context(16, mastery_by_topic=mastered))
        selected = {unit.topic_id for unit in curriculum.units}
        self.assertTrue(set(mastered).isdisjoint(selected))


class CurriculumLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/curriculum.db"
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO users (id, name) VALUES (?, ?)",
            ((1, "Owner"), (2, "Other")),
        )
        connection.executescript(
            """
            CREATE TABLE completed_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                lesson_id INTEGER NOT NULL,
                best_score INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, subject, lesson_id)
            );
            CREATE TABLE user_subject_progress (
                user_id INTEGER NOT NULL,
                subject TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT,
                PRIMARY KEY(user_id, subject)
            );
            CREATE TABLE user_plans (
                user_id INTEGER PRIMARY KEY,
                subject TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            );
            """
        )
        connection.commit()
        connection.close()
        self.repository = CurriculumRepository(self.db_path)
        self.repository.ensure_schema()
        self.taxonomy = load_math_taxonomy()
        self.progress_repository = CurriculumProgressRepository(self.db_path)
        self.progress_repository.ensure_schema()
        self.progress_service = CurriculumProgressService(
            self.progress_repository,
            taxonomy=self.taxonomy,
        )
        self.logger = logging.getLogger("tests.curriculum.lifecycle")
        self.logger.handlers = [logging.NullHandler()]
        self.logger.propagate = False

    def tearDown(self):
        self.temp_dir.cleanup()

    def service(self, *responses):
        gateway = FakeGateway(*(responses or (provider_failure(),)))
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=gateway, logger=self.logger),
            taxonomy=self.taxonomy,
        )
        return CurriculumService(
            engine,
            self.repository,
            progress_service=self.progress_service,
            taxonomy=self.taxonomy,
        ), gateway

    def create_published(self, context=None):
        service, _ = self.service()
        draft = service.generate_curriculum_draft(context or math_context())
        self.assertTrue(draft.success)
        published = service.publish_curriculum(
            user_id=1,
            curriculum_id=draft.value.id,
        )
        self.assertTrue(published.success)
        return service, published.value

    def test_draft_validation_publication_and_owner_boundary(self):
        service, gateway = self.service()
        draft = service.generate_curriculum_draft(math_context())
        self.assertTrue(draft.success)
        self.assertEqual(draft.value.status, CurriculumStatus.DRAFT)
        self.assertEqual(draft.value.curriculum_version, 1)
        self.assertEqual(len(gateway.calls), 1)

        unauthorized = service.publish_curriculum(
            user_id=2,
            curriculum_id=draft.value.id,
        )
        self.assertFalse(unauthorized.success)
        self.assertEqual(unauthorized.error.code, AIErrorCode.VALIDATION_ERROR)
        self.assertIsNone(self.repository.get_curriculum(2, draft.value.id))

        validated = service.validate_curriculum(user_id=1, curriculum_id=draft.value.id)
        self.assertTrue(validated.success)
        self.assertTrue(validated.value.validation.valid)
        self.assertEqual(validated.value.curriculum.status, CurriculumStatus.VALIDATED)

        published = service.publish_curriculum(user_id=1, curriculum_id=draft.value.id)
        self.assertTrue(published.success)
        self.assertEqual(published.value.status, CurriculumStatus.PUBLISHED)
        self.assertEqual(service.get_active_curriculum(user_id=1, subject="math").id, draft.value.id)

    def test_identical_draft_generation_is_idempotent(self):
        service, gateway = self.service(provider_failure(), provider_failure())
        first = service.generate_curriculum_draft(math_context())
        second = service.generate_curriculum_draft(math_context())
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(first.value.id, second.value.id)
        self.assertTrue(second.cached)
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(len(service.get_curriculum_history(user_id=1, subject="math")), 1)

    def test_republishing_backfills_progress_for_an_existing_active_curriculum(self):
        service, published = self.create_published()
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "DELETE FROM curriculum_progress_events WHERE curriculum_id = ?",
            (published.id,),
        )
        connection.execute(
            "DELETE FROM curriculum_checkpoint_progress WHERE curriculum_id = ?",
            (published.id,),
        )
        connection.execute(
            "DELETE FROM curriculum_unit_progress WHERE curriculum_id = ?",
            (published.id,),
        )
        connection.commit()
        connection.close()

        repeated = service.publish_curriculum(user_id=1, curriculum_id=published.id)
        self.assertTrue(repeated.success)
        snapshot = self.progress_service.get_curriculum_progress(
            user_id=1,
            curriculum_id=published.id,
        )
        self.assertEqual(snapshot.total_units, len(published.units))
        self.assertGreater(snapshot.available_units + snapshot.completed_units, 0)

    def test_new_publication_supersedes_old_and_preserves_version_history(self):
        service, first = self.create_published()
        first_progress = self.progress_service.get_curriculum_progress(
            user_id=1,
            curriculum_id=first.id,
        )
        self.assertEqual(first_progress.total_units, len(first.units))
        self.assertFalse(first_progress.historical)
        second_draft = service.generate_curriculum_draft(
            math_context(goal_score=190),
            generation_reason="target_score_changed",
        )
        self.assertTrue(second_draft.success)
        second = service.publish_curriculum(
            user_id=1,
            curriculum_id=second_draft.value.id,
        )
        self.assertTrue(second.success)
        self.assertEqual(second.value.curriculum_version, 2)
        previous = self.repository.get_curriculum(1, first.id)
        self.assertEqual(previous.status, CurriculumStatus.SUPERSEDED)
        self.assertEqual(self.repository.get_active(1, "math").id, second.value.id)
        history = self.repository.get_history(1, "math")
        self.assertEqual([item.curriculum_version for item in history], [2, 1])
        second_progress = self.progress_service.get_curriculum_progress(
            user_id=1,
            curriculum_id=second.value.id,
        )
        self.assertEqual(second_progress.total_units, len(second.value.units))
        self.assertFalse(second_progress.historical)
        self.assertTrue(self.progress_service.get_curriculum_progress(
            user_id=1,
            curriculum_id=first.id,
        ).historical)

    def test_failed_publication_rolls_back_superseding_the_active_version(self):
        service, first = self.create_published()
        second_draft = service.generate_curriculum_draft(
            math_context(goal_score=190),
            generation_reason="target_score_changed",
        )
        validated = service.validate_curriculum(
            user_id=1,
            curriculum_id=second_draft.value.id,
        )
        self.assertTrue(validated.success)

        connection = sqlite3.connect(self.db_path)
        connection.execute(f"""
            CREATE TRIGGER reject_test_curriculum_publish
            BEFORE UPDATE OF status ON ai_curricula
            WHEN NEW.id = '{second_draft.value.id}' AND NEW.status = 'published'
            BEGIN
                SELECT RAISE(ABORT, 'injected publication failure');
            END
        """)
        connection.commit()
        connection.close()

        failed = service.publish_curriculum(user_id=1, curriculum_id=second_draft.value.id)
        self.assertFalse(failed.success)
        self.assertEqual(failed.error.code, AIErrorCode.INTERNAL_ERROR)
        self.assertEqual(self.repository.get_active(1, "math").id, first.id)
        self.assertEqual(
            self.repository.get_curriculum(1, first.id).status,
            CurriculumStatus.PUBLISHED,
        )
        self.assertEqual(
            self.repository.get_curriculum(1, second_draft.value.id).status,
            CurriculumStatus.VALIDATED,
        )

    def test_database_constraints_prevent_two_published_curricula(self):
        service, first = self.create_published()
        second_draft = service.generate_curriculum_draft(
            math_context(goal_score=190),
            generation_reason="target_score_changed",
        )
        service.validate_curriculum(user_id=1, curriculum_id=second_draft.value.id)
        connection = sqlite3.connect(self.db_path)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE ai_curricula SET status = 'published' WHERE id = ?",
                (second_draft.value.id,),
            )
        connection.rollback()
        connection.close()
        self.assertEqual(self.repository.get_active(1, "math").id, first.id)

    def test_invalid_draft_is_rejected_and_cannot_be_published(self):
        service, _ = self.service()
        draft = service.generate_curriculum_draft(math_context())
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """
            UPDATE ai_curriculum_units SET priority = 'invalid-priority'
            WHERE curriculum_id = ? AND position = 1
            """,
            (draft.value.id,),
        )
        connection.commit()
        connection.close()

        rejected = service.validate_curriculum(user_id=1, curriculum_id=draft.value.id)
        self.assertFalse(rejected.success)
        self.assertEqual(rejected.error.code, AIErrorCode.VALIDATION_ERROR)
        self.assertEqual(
            self.repository.get_curriculum(1, draft.value.id).status,
            CurriculumStatus.REJECTED,
        )
        validation = self.repository.get_validation_result(1, draft.value.id)
        self.assertFalse(validation["valid"])
        self.assertIn("invalid_priority", {
            issue["code"] for issue in validation["issues"]
        })
        published = service.publish_curriculum(user_id=1, curriculum_id=draft.value.id)
        self.assertFalse(published.success)
        self.assertIsNone(self.repository.get_active(1, "math"))


class RegenerationDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = load_math_taxonomy()
        logger = logging.getLogger("tests.curriculum.regeneration")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        engine = CurriculumEngine(
            AIOrchestrator(_gateway=FakeGateway(provider_failure()), logger=logger),
            taxonomy=cls.taxonomy,
        )
        cls.active = engine.generate(math_context()).value
        cls.old_active = replace(
            cls.active,
            created_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        )

    def test_initial_manual_target_and_taxonomy_triggers(self):
        initial = should_regenerate_curriculum(
            None,
            self.taxonomy,
            RegenerationEvidence(initial_diagnostic_completed=True),
        )
        self.assertTrue(initial.should_regenerate)
        self.assertEqual(initial.trigger, "initial_diagnostic")

        manual = should_regenerate_curriculum(
            self.active,
            self.taxonomy,
            RegenerationEvidence(manual_requested=True),
        )
        self.assertEqual(manual.trigger, "manual_request")

        target = should_regenerate_curriculum(
            self.active,
            self.taxonomy,
            RegenerationEvidence(target_score_changed=True, previous_target_score=150),
        )
        self.assertEqual(target.trigger, "target_score_changed")

        stale = replace(self.active, taxonomy_version="old-taxonomy")
        taxonomy = should_regenerate_curriculum(
            stale,
            self.taxonomy,
            RegenerationEvidence(),
        )
        self.assertEqual(taxonomy.trigger, "taxonomy_updated")

    def test_minor_events_do_not_regenerate_and_material_events_respect_cooldown(self):
        minor = should_regenerate_curriculum(
            self.old_active,
            self.taxonomy,
            RegenerationEvidence(repeated_failure_count=2, mastery_delta=0.05),
        )
        self.assertFalse(minor.should_regenerate)
        self.assertEqual(minor.trigger, "no_material_change")

        failure = should_regenerate_curriculum(
            self.old_active,
            self.taxonomy,
            RegenerationEvidence(
                repeated_failure_topic_id="math.numbers.fractions",
                repeated_failure_count=3,
            ),
        )
        self.assertTrue(failure.should_regenerate)
        self.assertEqual(failure.trigger, "repeated_prerequisite_failure")

        mastery = should_regenerate_curriculum(
            self.old_active,
            self.taxonomy,
            RegenerationEvidence(mastery_delta=0.25, materially_updated_topic_count=3),
        )
        self.assertEqual(mastery.trigger, "major_mastery_update")

        cooldown = should_regenerate_curriculum(
            self.active,
            self.taxonomy,
            RegenerationEvidence(curriculum_completed=True),
        )
        self.assertFalse(cooldown.should_regenerate)
        self.assertEqual(cooldown.trigger, "cooldown")


if __name__ == "__main__":
    unittest.main()
