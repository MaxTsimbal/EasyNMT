# EasyNMT AI foundation

This package is the intelligence boundary for EasyNMT v1.0 Beta. It provides
the contracts that future AI-first learning modules use while preserving the
current Flask, SQLite, and server-rendered application.

Task 1 established the shared infrastructure. Task 2 added the production
mathematics curriculum domain. Task 3A connects published units to persistent,
server-authoritative progress and deterministic unlocking. Lesson, quiz, and
grading generation remain architectural contracts.
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

Generates a typed, versioned mathematics roadmap constrained to EasyNMT's
canonical taxonomy. Local policy owns topic eligibility and prerequisites;
OpenAI may only propose safe pacing, priority, and review placement. A
deterministic fallback uses the same validation path. The application service
owns draft validation and atomic publication. See
[`curriculum/README.md`](curriculum/README.md) for taxonomy, persistence,
lifecycle, regeneration, and Task 3 integration details.

### `LessonEngine`

Expands one `LearningPlan` into a complete `Lesson`. Its generation path is
cache-ready. It cannot mark a lesson complete.

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

Reusable models live in `models.py`: `Lesson`, `Quiz`, `Question`, `Curriculum`,
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
