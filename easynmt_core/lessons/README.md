# Production curriculum lessons

Task 3B turns a published curriculum unit into a complete, validated teaching
artifact. This package is the application boundary around the AI
`LessonEngine`; it owns persistence, delivery evidence, authorization checks,
and the handoff to `CurriculumProgressService`. It never calculates XP,
mastery, unlocking, or assessment results.

Active dashboard, Today, Library, and Planner navigation uses production
curriculum unit IDs whenever the signed-in learner has a published curriculum.
The numeric `/lesson/<id>` experience remains available only as a compatibility
fallback for existing users and old URLs that do not yet have a published
curriculum.

## Lesson lifecycle

```text
published curriculum + taxonomy + owner-scoped progress
                         |
                         v
              LessonGenerationRequest
                         |
                         v
                   LessonEngine
                         |
             one structured AI request
                         |
                         v
              deterministic validation
                         |
                         v
          immutable SQLite lesson artifact
                         |
                authenticated delivery
                         |
        hashed server-issued completion token
                         |
                         v
       CurriculumProgressService (same transaction)
         in_progress -> lesson_completed
                     -> assessment_required
```

A unit must already be `in_progress` before generation. Lessons remain readable
in `lesson_completed`, `assessment_required`, and `completed` for review, but a
new completion token is issued only while the unit is `in_progress`. Locked,
available, review-required, historical, wrong-owner, and wrong-subject units
are rejected before an AI request.

## Educational contract

`easynmt_ai.lessons` defines immutable nested models for concepts, examples,
mistakes, tips, guided practice, recap, readiness, and the assessment blueprint. Every
accepted lesson always has this order:

1. learning objective;
2. NMT relevance;
3. prerequisite reminder (the UI explicitly states when none is required);
4. progressive core explanation;
5. foundation, guided, and exam worked examples;
6. diagnosed common mistakes;
7. practical tips;
8. three independent practice tasks ordered foundation, guided, and exam;
9. mini recap;
10. assessment transition.

The validator checks authoritative curriculum identity, objective and
competency coverage, explanation depth, distinct example progression,
step-by-step reasoning, independent verification, concept references, mistake
diagnosis, guided-practice uniqueness and concept coverage, recap completeness,
and exact assessment-blueprint coverage.
Structurally valid but educationally incomplete AI output is rejected and is
never persisted. Local development has a reviewed Mathematics entry lesson and
a subject-aware deterministic recovery path for every application-owned topic
in the Mathematics, Ukrainian, History, and English taxonomies. Recovery uses
only authoritative topic identity, objectives, competencies, vocabulary,
example seeds, and common-mistake seeds. Invented topic IDs or stale/mismatched
metadata are rejected rather than turned into plausible-looking content. The
fallback passes the same typed model and validator, is stored as immutable
structured content, and is disabled whenever `RAILWAY_ENVIRONMENT` is present.
It can also be disabled locally with
`EASYNMT_ALLOW_DEVELOPMENT_LESSON_FALLBACK=0`.

## AI and cache pipeline

`LessonEngine` calls only `AIOrchestrator`; routes and this service never call
OpenAI. Prompt responsibilities are separate reusable functions for
explanation, examples, mistakes/tips, guided practice, recap/assessment, and tutor voice. They
are composed into one structured request so sections share context and no
unnecessary provider calls occur.

The request fingerprint includes prompt/schema versions, model, authoritative
unit inputs, and a bounded learner snapshot. It excludes raw mistakes, XP, and
user identity. A valid lesson is stored once under that fingerprint. The
SQLite cache works across restarts and Gunicorn threads; an in-process keyed
lock coalesces concurrent first requests within a worker. The engine still
implements the general `AICache` contract so a later Redis layer does not
require a lesson-contract change.

## Completion and security

Each active delivery creates a random bearer token. Only its SHA-256 hash is
stored. The delivery binds owner, published curriculum, unit, immutable lesson
ID, content hash, and a unique evidence ID. Completion accepts no client state,
score, XP, mastery, or lesson content—only the token from the authenticated
session.

Completion runs in one `BEGIN IMMEDIATE` transaction:

1. verify token, owner, unit, subject, active curriculum, and both stored
   content hashes;
2. construct typed `SERVER_LESSON` evidence using the server timestamp;
3. ask `CurriculumProgressService` to move the unit to
   `assessment_required`;
4. consume the delivery and append the lesson audit event;
5. commit all changes together.

Any error rolls back delivery, progress transitions, and audit events. Reusing
the same consumed token returns the original completion result without a new
progress event. Lesson completion awards no XP and does not establish a
mastery score; assessment remains the only route to those effects.

Routes are:

- `POST /curriculum/units/<unit_id>/start` for server-rendered navigation;
- `GET /curriculum/units/<unit_id>/lesson`;
- `POST /curriculum/units/<unit_id>/lesson-complete`;
- `GET /api/curriculum/units/<unit_id>/lesson`;
- `POST /api/curriculum/units/<unit_id>/lesson-complete`.

All require authentication. POST routes use the existing global CSRF guard.
The HTML start route accepts only the CSRF field, delegates the state change to
`CurriculumProgressService`, and redirects to lesson delivery. API errors are
stable JSON envelopes; the UI renders an appropriate error page.

## Persistence and rollback

`CurriculumLessonRepository.ensure_schema()` is a repeatable startup migration.
It creates the lesson tables when absent and safely expands the original
`generation_source='openai'` constraint to accept reviewed deterministic local
artifacts while preserving existing rows. It owns:

- `curriculum_lessons`: immutable validated content, fingerprint, hash, model,
  schema/prompt versions, token usage, and provider response ID;
- `curriculum_lesson_deliveries`: hashed token and immutable completion
  evidence binding;
- `curriculum_lesson_events`: generated, cache, delivery, failure, and
  completion audit events;
- owner/unit/fingerprint, topic, delivery, and event indexes.

Foreign keys bind rows to existing users, curriculum owners, units, and lesson
artifacts. No legacy table or row is modified by the migration.

To reverse Task 3B before another subsystem depends on these rows, back up the
database, stop the application, and run inside one transaction in this order:

```sql
DROP TABLE IF EXISTS curriculum_lesson_events;
DROP TABLE IF EXISTS curriculum_lesson_deliveries;
DROP TABLE IF EXISTS curriculum_lessons;
```

Dropping these tables removes generated lesson and completion-evidence history,
so rollback is an explicit operator action, never application startup logic.

## Task 3C handoff

Task 3C should consume `Lesson.for_quiz()`. It receives typed objectives,
competencies, concepts, examples, mistakes, guided practice, recap, and an assessment blueprint;
it never parses rendered text or persistence metadata. The Quiz/Grading service
must issue its own server-verified attempt result and pass that to
`CurriculumProgressService`. It must not infer completion from the lesson token
or award XP directly.
