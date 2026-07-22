# Production curriculum engine

This package owns Mentory's versioned mathematics-roadmap domain. It remains
separate from the legacy three-lesson UI catalog, while Task 3A now connects a
published version to dedicated curriculum-unit progress without changing the
current lesson pages or dashboard.

OpenAI proposes pacing and priority within application-owned constraints. It
cannot define topics, prerequisites, curriculum identifiers, versions,
lifecycle state, user ownership, or publication state.

## Taxonomy

`data/math_v1.json` is the canonical, versioned taxonomy. The initial internal
version contains 39 topics across the principal mathematics domains used for
NMT preparation. Its completeness note explicitly avoids claiming that it is
an official or final NMT specification.

Every topic has:

- `subject`, stable `id`, and stable `slug`;
- Ukrainian title and description;
- domain, difficulty, and estimated study minutes;
- authoritative prerequisite topic IDs;
- learning objectives and target competencies;
- a required/optional flag;
- softer `recommended_after_topic_ids` ordering constraints.

`taxonomy.py` rejects missing fields, duplicate IDs/slugs, invalid identifiers,
unknown dependencies, self-dependencies, prerequisite cycles, and cycles formed
by combined prerequisite/recommended ordering.

The old numeric math lessons do not define this taxonomy. Their only bridge is
`LEGACY_MATH_LESSON_TOPIC_MAP`, which records the current semantic mapping:

- legacy lesson 1 → quadratic equations;
- legacy lesson 2 → linear equations;
- legacy lesson 3 → functions and graphs.

### Changing the taxonomy

1. Add or edit topics in a new versioned JSON file; never reuse a stable ID for
   a different concept.
2. Increment the taxonomy version.
3. Point the loader at the reviewed version.
4. Run the taxonomy and golden curriculum tests.
5. Review every prerequisite and recommended-order edge with a mathematics
   subject expert before release.
6. Trigger regeneration through the `taxonomy_updated` decision; do not mutate
   published historical curricula.

The loader is data-driven, so adding a valid domain or topic does not require
engine changes.

## Generation policy

`policy.py` deterministically derives the candidate and required topic sets
from `AIContext`:

- target scores through 150 use foundation topics;
- targets from 151 through 189 add intermediate depth;
- targets of 190 or higher allow the full advanced/optional set;
- completed/mastered topics are removed unless weakness or scheduled review
  justifies them;
- known weakness text and recognizable recent-mistake text are reduced locally
  to canonical topic IDs; raw answers are not sent to OpenAI;
- the prerequisite closure is always included and topologically ordered;
- diagnostic data determines beginner/average/strong starting level when an
  explicit level is absent;
- study time limits sessions to 45 or 60 minutes;
- an exam date adds a total time-capacity validation.

The AI receives only allowed taxonomy entries, deterministic policy fields,
bounded diagnostic/mastery data, study capacity, and a minimal active-roadmap
summary. It may propose priorities, safe durations, session counts, optional
allowed topics, and review placement. Every required topic must appear once.

The versioned strict-output contract in `prompts/curriculum.py` accepts only
units and review checkpoints. The engine supplies all authoritative metadata
locally, parses the result into shared typed models, and runs deterministic
validation before returning a draft.

If provider execution fails, times out, is rate limited, returns invalid JSON,
or violates the contract, the engine can produce a safe deterministic draft.
`generation_metadata.source` distinguishes `openai` from `deterministic`, and
the provider error is preserved as a structured warning. A fallback that cannot
pass the same validation is returned as an error and is never persisted or
published.

## Validation boundaries

Before publication, local validation rejects:

- empty, duplicate, unknown, or target-incompatible units;
- missing required topics or unmet/out-of-order prerequisites;
- recommended-order violations;
- altered authoritative prerequisites or difficulties;
- malformed priorities/reason codes and unjustified mastered topics;
- durations outside the taxonomy's bounded range;
- sessions above the learner workload limit;
- incompatible mastery targets;
- invalid/future checkpoint topics, review gaps over six units, or missing final
  reviews;
- curricula that cannot fit the available weeks and study minutes.

OpenAI never changes state. A proposal always starts as `draft`.

## Lifecycle and persistence

The state machine is:

```text
draft ──valid──> validated ──publish──> published ──replacement──> superseded
  └──invalid──> rejected
```

SQLite remains authoritative. `CurriculumRepository.ensure_schema()` follows
the existing repository-managed schema convention and creates:

- `ai_curricula` for version/lifecycle/generation/validation metadata;
- `ai_curriculum_units` for canonical ordered units;
- `ai_curriculum_checkpoints` for reviews;
- `ai_curriculum_events` for an append-only transition audit.

Every curriculum is immutable in identity and version. The repository assigns
the next per-user/per-subject version under `BEGIN IMMEDIATE`. A unique
generation fingerprint prevents duplicate drafts, and a partial unique index
allows only one published curriculum per user and subject. Publishing
supersedes the old active version and publishes the replacement in one
transaction; an error rolls back both changes. Old versions remain available
through history for audit and a future explicit rollback workflow.

## Application service

`CurriculumService` is the API intended for future Flask or job-runner code:

- `generate_curriculum_draft(...)`;
- `validate_curriculum(...)`;
- `publish_curriculum(...)`;
- `get_active_curriculum(...)`;
- `get_curriculum_history(...)`;
- `should_regenerate_curriculum(...)`.

All reads and transitions are scoped by `user_id`; a caller cannot retrieve or
publish another user's curriculum by knowing its ID. Expected provider,
validation, transition, and database failures use `EngineResult`/`AIError`
instead of escaping into a Flask request.

The service is initialized in `app.py`. Task 3A adds read/start routes through
the separate progress service; curriculum generation/publication still has no
public browser mutation route.

## Regeneration

Regeneration is a read-only decision until application code explicitly requests
a new draft. Deterministic triggers are:

- first completed diagnostic;
- target-score change;
- at least three failures in a prerequisite topic;
- mastery delta of at least 0.20 or at least three materially changed topics;
- completed active curriculum;
- manual request;
- taxonomy-version change.

Minor changes return `no_material_change`. Automatic failure/mastery/completion
triggers use a 24-hour cooldown by default. Context and request fingerprints,
which include taxonomy, prompt, schema, model, and reason versions, provide
additional deduplication.

## Curriculum progress and future LessonEngine integration

Task 3A consumes only units from the owner's `published` curriculum. A
published unit supplies the stable taxonomy topic ID, difficulty, objectives,
prerequisites, priority, and mastery target needed to construct a lesson
request. Lesson generation must not mark the unit complete, unlock another
unit, award XP, or alter curriculum state; those remain transactional Flask and
SQLite responsibilities.

Publication now initializes the versioned progress tables in the same
transaction that supersedes the old curriculum. Canonical prerequisite topics
and checkpoints control unlocks; numeric legacy lesson order does not. The full
state, migration, XP, concurrency, and authorization policy is documented in
[`../../easynmt_core/progress/README.md`](../../easynmt_core/progress/README.md).
Task 3B should issue typed lesson evidence through that service and must not
infer completion from AI output.

## Development bootstrap and status

The Flask CLI provisions owner-scoped roadmaps for Mathematics, Ukrainian,
History, and English through the same deterministic engines, validators, shared
repository, publication transition, and `CurriculumProgressService` hook used
by application code. It never deletes a user, replaces a valid published
curriculum, or rewrites existing progress. Repeated runs reuse valid data;
repair is limited to missing rows from a deterministic baseline whose immutable
identity still matches.

```powershell
$repo = 'C:\path\to\Mentory_Public'
Set-Location -LiteralPath $repo
.\.venv\Scripts\python.exe -m flask --app app curriculum status
.\.venv\Scripts\python.exe -m flask --app app curriculum bootstrap-development --all-subjects
.\.venv\Scripts\python.exe -m flask --app app curriculum status
.\.venv\Scripts\python.exe app.py
```

Use repeatable `--subject math`, `--subject ukrainian`, `--subject history`, or
`--subject english` options to provision a selected subset. Omitting both
`--subject` and `--all-subjects` preserves the original Mathematics-only
behavior. Every result line reports learner, subject, curriculum, publication
state, repair counts, and stable unit IDs.

Both commands report the resolved database target. Locally that is
`instance\users.db` unless `EASYNMT_DB_PATH` or
`RAILWAY_VOLUME_MOUNT_PATH` is set, exactly matching `python app.py`.

Bootstrap is never automatic. On Railway or an explicitly named production
environment, an administrator must supply both independent overrides in a
one-off administrative job:

```powershell
$env:EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP = '1'
.\.venv\Scripts\python.exe -m flask --app app curriculum bootstrap-development --all-subjects --allow-production
Remove-Item Env:EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP
```

Inspect status before and after the job. Do not place the override in normal
deployment configuration or startup commands.
