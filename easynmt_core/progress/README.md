# Curriculum unit progress

This package makes a published curriculum executable without giving AI or the
browser authority over learner state. `CurriculumProgressService` is the only
application boundary that mutates curriculum-unit progress. Policy code decides
valid transitions, the repository owns SQLite persistence, and routes only
validate authenticated input and call the service.

```text
CurriculumService
      |
      v
CurriculumProgressService ---> ProgressPolicy
      |
      v
CurriculumProgressRepository
      |
      v
SQLite

Production Lesson service / Quiz Engine / Grading Engine
      |
      v
typed, server-verified evidence
      |
      v
CurriculumProgressService
```

AI cannot initialize progress, choose a state, calculate an unlock, change
mastery, or award XP. Client requests cannot submit those values either. The
Task 3B is the first trusted production caller: its server-issued, owner-bound
delivery evidence can complete a lesson. Assessment completion remains internal
until Task 3C supplies a trusted quiz/grading caller.

## State machine

| Current state | Allowed next state | Authority and evidence |
| --- | --- | --- |
| `locked` | `available` | Deterministic prerequisite/checkpoint recalculation only |
| `available` | `in_progress` | Authenticated owner starts the unit |
| `in_progress` | `lesson_completed` | Typed server or validated legacy lesson evidence |
| `lesson_completed` | `assessment_required` | Application service after lesson completion |
| `assessment_required` | `completed` | Typed server-verified passing assessment |
| `completed` | `review_required` | Explicit typed review policy reason |
| `review_required` | `in_progress` | Owner starts a review lesson |
| `review_required` | `completed` | Typed server-verified passing review |

A failed assessment remains `assessment_required`; a failed direct review
remains `review_required`. Invalid jumps, writes to locked units, stale
compare-and-set updates, wrong-owner access, and writes to superseded curricula
raise typed domain errors.

## Persistence

`CurriculumProgressRepository.ensure_schema()` is additive and repeatable. It
creates:

- `curriculum_unit_progress`: one owner/curriculum/unit row, state, mastery,
  attempts, XP marker, timestamps, source, and optimistic version;
- `curriculum_checkpoint_progress`: checkpoint state, attempts, timestamps, and
  optimistic version;
- `curriculum_topic_credits`: explicit canonical-topic evidence carried from a
  legacy completion, prior curriculum, or generation mastery snapshot;
- `curriculum_assessment_results`: immutable server-verified attempts with a
  globally unique attempt ID;
- `curriculum_progress_events`: append-only state, unlock, migration, attempt,
  and XP audit events.

Composite foreign keys bind progress to the same user that owns the curriculum.
Other constraints validate states, mastery range, non-negative attempts/XP,
assessment scores, and exactly one assessment target. Indexes cover active
state, topic, checkpoint, assessment, and audit lookups. Existing legacy tables
are not overwritten or deleted.

## Publication and initialization

Curriculum publication and progress initialization share one `BEGIN IMMEDIATE`
transaction. Publishing a replacement performs all of these operations or none:

1. supersede the old published curriculum;
2. publish the validated replacement;
3. create every unit and checkpoint progress row;
4. record conservative topic credits and migration events;
5. calculate initial availability.

Initialization accepts only the owner's published curriculum. Stable row IDs,
unique constraints, exact row-count checks, and event keys make a repeated call
idempotent. A partially initialized curriculum is rejected rather than filled
silently, so an injected error cannot leave a mixed generation of rows.

## Unlocking

`recalculate_unlocks()` runs transactionally and only changes `locked` to
`available`. A unit is eligible when:

- its curriculum is the owner's active published version;
- every canonical prerequisite in the transitive taxonomy closure is satisfied;
- any checkpoint before the unit's presentation position is completed; and
- the unit is still locked rather than completed, active, or under review.

Canonical topic IDs, not numeric lesson/unit order, establish prerequisites.
Order is used only to determine which later units a checkpoint gates. Multiple
branches and optional units can unlock in the same calculation. Recalculation
uses compare-and-set writes and stable event keys, so repeats do not duplicate
state changes or audit entries.

An explicit credit can satisfy an omitted prerequisite topic. If that credited
topic is present as a `review_required` unit, its dependents stay locked until
the review is verified; the credit does not bypass the review policy.

## Mastery

Mastery uses both a validated score from `0.0` through `1.0` and these bands:
`unknown`, `introduced`, `developing`, `proficient`, `mastered`, and
`needs_review`.

Lesson completion establishes only `introduced`. A failed assessment can add
bounded developing evidence up to `0.49`. One passing assessment can establish
proficiency from `0.65` through `0.85`, but never full mastery. Updates are
monotonic in Task 3A and every assessment is persisted with an audit event.
This is intentionally conservative; adaptive decay and multi-attempt mastery
aggregation belong to later grading work.

## XP and concurrency

A first passing, server-native curriculum assessment awards 60 completion XP,
matching the existing legacy first-pass cap. The progress row's `xp_awarded`
marker, unique assessment attempt ID, current-state compare-and-set, and
`BEGIN IMMEDIATE` prevent duplicate awards across retries and parallel tabs.
Progress, assessment evidence, subject XP, legacy plan XP, unlocks, and events
commit in one transaction, so a later failure rolls back the XP change too.

`legacy_quiz` evidence awards zero curriculum XP because the existing quiz
finalizer already owns that award. Matching stored legacy completion is required
before such evidence is accepted. Migrated/credited units also award zero new
XP. Historical XP is never recalculated or removed.

All mutation methods accept an optional expected version. A retry carrying the
same immutable evidence remains idempotent even if that version is now stale;
a different action using stale state returns `ProgressConflict`. Reusing an
evidence/attempt ID with different facts is rejected.

## Curriculum replacement

Replacement never copies unit position or opaque state. Initializing the new
version considers, in increasing precedence:

1. generation-time mastered topic snapshots;
2. the explicit legacy math lesson-to-topic mapping;
3. completed canonical topic IDs from prior superseded curricula.

A matching ordinary unit is credited `completed`; a matching
`review_mastered` unit starts `review_required`. Credits carry no XP and record
their source/reference. Unrelated topics remain locked or become available only
through normal prerequisite calculation. Old progress and its timestamps/events
remain readable with `historical=True`, but superseded versions reject normal
writes.

## Legacy compatibility

The server-rendered legacy lessons, `completed_lessons`, quiz attempts,
`lesson_readiness`, numeric legacy unlocking, and dashboard data remain in
place. They continue to drive the current UI. For curriculum progress, the
canonical bridge is deliberately small:

- lesson 1 -> `math.algebra.quadratic_equations`;
- lesson 2 -> `math.algebra.linear_equations`;
- lesson 3 -> `math.functions.concept_graphs`.

Only a stored completion with a matching subject, lesson ID, user, and canonical
topic is accepted as legacy evidence. Numeric legacy order never unlocks a
curriculum unit. A later UI migration can retire the legacy path only after its
lesson, assessment, and dashboard consumers use this service.

## API and authorization

The curriculum progress and Task 3B lesson integration exposes:

- `GET /api/curriculum/progress` for the signed-in user's active session subject;
- `POST /api/curriculum/units/<unit_id>/start` with optional
  `expected_version`.
- `GET /api/curriculum/units/<unit_id>/lesson` for a validated lesson and
  server-issued delivery token;
- `POST /api/curriculum/units/<unit_id>/lesson-complete` with only that token.

Unsafe API calls require CSRF. Session identity is authoritative; the start
route rejects extra keys such as `user_id`, state, score, mastery, or XP. Owner,
active-curriculum, unit, and session-subject checks occur again inside the
transaction. Expected failures map to stable JSON error codes without raw SQL
or exception details.

## Audit and privacy

Events contain only relevant identifiers, previous/new state, reason, attempt
or idempotency key, XP delta, safe metadata, and timestamp. Raw written answers,
prompts, uploads, and image contents are not stored in progress events.

## Known limitations and next integrations

- `ServerVerifiedAssessmentResult` is a security contract, not the final AI
  grading system.
- There is no public assessment-result route because the production
  Quiz/Grading caller belongs to Task 3C.
- Mastery policy is deliberately conservative and does not implement decay.
- The current dashboard still reads the legacy progress model; the new snapshot
  is ready for a later UI migration.
- SQLite is appropriate for the current single-database deployment. A future
  multi-process/distributed store must preserve the same transaction,
  idempotency, and ownership semantics.

Task 3B connects through the caller-owned transaction method
`complete_lesson_for_assessment_in_transaction()`. It supplies typed immutable
evidence while this service remains the only code that changes progress state.
See [`../lessons/README.md`](../lessons/README.md).
