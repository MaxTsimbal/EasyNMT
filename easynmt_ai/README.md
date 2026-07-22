# Mentory AI foundation

This package is the intelligence boundary for Mentory v1.0 Beta. It provides
the contracts that future AI-first learning modules use while preserving the
current Flask, SQLite, and server-rendered application.

Task 1 established the shared infrastructure. Task 2 added the production
mathematics curriculum domain. Task 3A connects published units to persistent,
server-authoritative progress and deterministic unlocking. Task 3B adds the
production Lesson Engine, immutable lesson cache, and trusted completion
handoff. Quiz and grading generation remain architectural contracts.
Existing tutor, lesson-chat, and photo-grading behavior continues through the
same orchestrator.

## Boundary and data flow

```text
Flask route or application service
        |
        | AIContext + typed input
        v
Independent engine --------> dedicated prompt module
        |
        v
AIOrchestrator -------------> cache contract
        |
        v
private Responses API adapter
        |
        v
OpenAI Responses API
```

`AIOrchestrator` is the only public component allowed to execute an OpenAI
request. `service.py` is its private provider adapter; no route, page, or engine
may import or call it. The boundary is enforced by
`tests/test_ai_architecture.py`.

Flask and SQLite remain authoritative for authentication, permissions, lesson
unlocking, quiz finalization, progress, XP, quotas, and persistence. Curriculum
engines cannot mutate the progress subsystem documented in
[`../easynmt_core/progress/README.md`](../easynmt_core/progress/README.md). AI
output is untrusted proposed content until the application validates and accepts
it.

## Components

### `AIOrchestrator`

Owns provider configuration and execution, structured-output decoding, stable
errors, request telemetry, and cache integration. It also preserves the current
conversation persistence workflow for the tutor.

Every real provider invocation emits one centralized log record with:

- `ai_engine`
- `ai_execution_ms`
- `ai_token_usage`, when returned by the provider
- `ai_success`
- `ai_user_id`
- `ai_error_code`
- `ai_response_id`

Prompts, answers, uploaded image data, credentials, and full learner history are
not written to this telemetry record.

### `CurriculumEngine`

Generates a typed, versioned mathematics roadmap constrained to Mentory's
canonical taxonomy. Local policy owns topic eligibility and prerequisites;
OpenAI may only propose safe pacing, priority, and review placement. A
deterministic fallback uses the same validation path. The application service
owns draft validation and atomic publication. See
[`curriculum/README.md`](curriculum/README.md) for taxonomy, persistence,
lifecycle, regeneration, and Task 3 integration details.

### `LessonEngine`

Expands an authoritative `LessonGenerationRequest` into a complete structured
`Lesson`. A compatibility adapter still accepts Task 1 `LearningPlan` callers.
Separate explanation, example, mistake/tip, recap/assessment, and tutor-voice
prompt responsibilities are composed into one structured request. The engine
binds provider output to local curriculum identity and validates educational
sufficiency plus exact Task 3C concept coverage. Invalid output has no
placeholder fallback. The engine cannot mark a lesson complete. Persistence
and delivery are documented in
[`../easynmt_core/lessons/README.md`](../easynmt_core/lessons/README.md).

### `QuizEngine`

Creates a lesson-bound `Quiz` and reusable `Question` models. It does not expose
a route, create an attempt, or decide whether an attempt is finalized.

### `GradingEngine`

Checks answers against the supplied immutable quiz contract and returns a typed
`GradeResult` with `Feedback`. It cannot award XP, mutate weaknesses, or unlock
content. The existing photo grader is a compatibility facade that also calls
the orchestrator and uses the grading prompt layer.

## Shared context and models

`AIContext` is an immutable snapshot containing:

- user ID and subject;
- goal score and current lesson;
- completed lesson IDs;
- known weaknesses and recent mistakes;
- XP, language, and difficulty;
- the available output-token budget.
- canonical topic completion/mastery and diagnostic results;
- study capacity, desired exam date, and active curriculum identity.

`LearningContext` extends this contract with fields required by the existing
tutor UI. It normalizes legacy subject, goal, and lesson values into the shared
fields so old routes and new engines can coexist.

Reusable models live in `models.py` and the focused `lessons/models.py` module:
`Lesson`, its nested teaching structures, `Quiz`, `Question`, `Curriculum`,
`CurriculumUnit`, `ReviewCheckpoint`, `GradeResult`, `Feedback`, and
`LearningPlan`. Each model validates untrusted provider data and can serialize
across the cache boundary.

## Prompt layer

Prompt construction belongs in `prompts/`, never in Flask routes or engines:

- `curriculum.py`
- `lesson.py`
- `quiz.py`
- `grading.py`
- `builder.py` for the existing tutor

Each new engine prompt returns a `PromptSpec` containing instructions, user
input, a schema name, and a strict JSON Schema. The internal adapter submits
that schema using Responses API Structured Outputs. The orchestrator still
validates JSON and domain models because provider output must never be trusted
at a persistence boundary.

## Errors

Engines return `EngineResult[T]`; expected provider failures do not escape into
Flask as exceptions. Stable `AIErrorCode` values cover:

- disabled provider;
- timeout;
- rate limit;
- provider/API failure;
- empty response;
- invalid JSON;
- domain validation failure;
- unexpected internal failure.

`AIError.retryable` lets future queue or UI layers decide whether to retry. Error
messages are provider-neutral and do not expose credentials or raw SDK details.

## Caching

Engines depend on the `AICache` protocol. The default `NullAICache` does not
store data. Cache keys are deterministic SHA-256 hashes of versioned generation
inputs. A future Redis implementation can replace the default without changing
an engine. Grading is intentionally uncached because answers and attempt state
are request-specific.

Task 3B also provides a persistent SQLite acceptance cache outside this generic
hook. Only lessons that pass domain validation are stored, preventing repeat
generation across application restarts. A future Redis implementation can add
distributed request coalescing while SQLite remains the durable artifact store.

## Adding an engine

1. Add the reusable input/output model to `models.py` with `from_dict()` and
   `to_dict()` behavior.
2. Add a dedicated `prompts/<engine>.py` returning a `PromptSpec` with a strict
   schema.
3. Add an `AIEngine` subclass in `engines/`. Give it a stable `name` and optional
   cache namespace/TTL.
4. Call only `AIOrchestrator.execute_structured()` or another public
   orchestrator method. Never import `service.py` or the OpenAI SDK.
5. Return `EngineResult[T]`. Do not mutate Flask sessions or SQLite from an
   engine.
6. Add contract, malformed-response, cache, telemetry, and boundary tests.
7. Connect a route only after application-level authorization, quota, and
   persistence behavior has been designed.

## Verification

Run the complete regression suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

The architecture tests use an injected fake gateway. They never require an API
key and never make paid network calls.

## Task 4B: Easy Intelligence Core

Tutor turns now pass through a deterministic intelligence layer before the
provider boundary. `intelligence.py` creates a bounded `LearnerMemory` and a
`TutorExecutionPlan` without making another model call.

The plan routes a request to one of four profiles:

- `fast` for short, low-complexity questions;
- `balanced` for normal tutoring;
- `deep` for multi-step solving, review, and explanation retries;
- `vision` for image-supported learning work.

Provider settings may map each profile to a different model. All profile
settings fall back to `OPENAI_MODEL`, so deployment behavior remains unchanged
until an operator explicitly opts into tiered models. Reasoning effort and text
verbosity are attached only to model families known to support those controls.

`ai_learner_memory` stores only explicit subject-scoped teaching preferences,
step-by-step needs, explanation retry count, and last lesson focus. It does not
store authority over assessment state. Flask/SQLite still owns scores, XP,
unlocks, quotas, and permissions.

The tutor prompt receives server-authoritative curriculum completion, mastery,
diagnostic, goal, lesson, weakness, and recent-mistake signals. Outputs are
locally normalized to remove canned conversational shells before persistence.
Routing metadata records only profile and complexity, never full prompts,
credentials, or private history.
