# Mentory

Mentory is a Flask and SQLite learning platform for structured NMT preparation.
The active product path combines curated lessons, server-generated quizzes,
per-subject progress, mistake review, and an optional OpenAI-powered tutor.

This repository is the cumulative `1.0.0-beta.2` candidate. Local development
can still run without an OpenAI key and exposes a truthful offline mode. A
Railway Beta deployment requires OpenAI by default because written grading,
lesson generation, and the final photo solution are part of the accepted
learning journey.

## Architecture

- `app.py` — Flask routes, authentication, onboarding, lesson flow, quiz
  finalization, progress views, and API orchestration.
- `learning_engine.py` — canonical quiz construction and deterministic grading.
- `easynmt_ai/` — central AI orchestrator, canonical four-subject registry,
  versioned Mathematics, Ukrainian, History, and English taxonomies, shared
  context/models, independent engine contracts, prompt layer, cache boundary,
  conversation repository, attachment validation, and streaming support.
- `easynmt_core/health.py` — separate liveness and release-readiness endpoints.
- `easynmt_core/beta_readiness.py` — SQLite integrity, persistent-storage,
  backup, provider, and single-worker release gates plus verified hot backups.
- `easynmt_core/lessons/` — production curriculum lesson persistence, secure
  delivery evidence, rendering, and the Task 3A completion handoff.
- `easynmt_core/quizzes/` — Task 3C.1 production quiz snapshots, sessions,
  deterministic server grading, drafts, attempts, XP, and atomic unlocks.
- `easynmt_core/contextual_easy.py` — lesson-aware Easy assistance and a
  restricted quiz-help boundary with server-side answer-leak protection.
- `templates/` and `static/` — server-rendered UI and browser behavior.
- `tests/` — security, quiz consistency, persistence, API, and route regression
  coverage.

`easynmt_core/progress/` owns server-authoritative curriculum-unit state,
deterministic prerequisite/checkpoint unlocking, mastery, XP compatibility,
audit events, and future-UI read models.

The production Lesson Engine turns an in-progress curriculum unit into a
complete structured lesson, validates educational sufficiency, and caches the
accepted artifact in SQLite. It uses one OpenAI request through the central
orchestrator. Local development can use validator-backed, subject-aware
deterministic lessons grounded in the application-owned taxonomy metadata when
OpenAI is unavailable. Caller-invented topics and stale topic metadata are
rejected instead of fabricated. Legacy numeric lessons remain only for learners
without an applicable published curriculum.

SQLite is authoritative for progress, quiz attempts, unlock state, AI history,
and quotas. Flask's signed session stores identity and lightweight navigation
state; it is not trusted as the source of XP or completion data. Production
quizzes contain 12 questions worth 24 points, require 18 points to pass, and
commit the attempt, XP, completion, and next-unit unlock atomically.



## Task 5 · v1.0 Beta readiness

Task 5 adds a deterministic release gate, verified SQLite backups, request IDs,
release headers, and CLI smoke commands. It does not call Google or OpenAI from
`/ready`; it checks that required configuration is present and that the local
runtime is safe.

```powershell
.\.venv\Scripts\python.exe -m flask --app app beta check
.\.venv\Scripts\python.exe -m flask --app app beta backup --reason before-release
.\.venv\Scripts\python.exe -m flask --app app beta smoke
```

See [INSTALL_TASK_5_V1_BETA_READINESS.md](INSTALL_TASK_5_V1_BETA_READINESS.md),
[TASK_5_V1_BETA_READINESS_REPORT.md](TASK_5_V1_BETA_READINESS_REPORT.md), and
[BETA_MANUAL_TEST_CHECKLIST.md](BETA_MANUAL_TEST_CHECKLIST.md).

## Task 3C final candidate

Production quizzes now grade ordinary learner wording instead of requiring a
near-verbatim copy of the reference answer. Correct final results receive their
core credit, while reasoning earns the remaining points. Late-quiz prompts are
concrete tasks rather than labels for a skill.

Contextual Easy is embedded directly in production lessons and quizzes. Lesson
mode can teach from the current lesson and active section. Quiz mode is bound to
the server-validated active question and may simplify the instruction, define a
term, remind the relevant general rule, or demonstrate a genuinely different
example. It cannot reveal, confirm, eliminate toward, or solve the current
answer. The server excludes answer-key fields from the AI context, blocks direct
answer requests before model use, and checks generated output for leaks.

See [INSTALL_TASK_3C_FINAL.md](INSTALL_TASK_3C_FINAL.md) and
[TASK_3C_FINAL_REPORT.md](TASK_3C_FINAL_REPORT.md).

## Local setup

```powershell
$repo = 'C:\path\to\Mentory_Public'
Set-Location -LiteralPath $repo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m flask --app app curriculum status
.\.venv\Scripts\python.exe -m flask --app app curriculum bootstrap-development --all-subjects
.\.venv\Scripts\python.exe -m flask --app app curriculum status
.\.venv\Scripts\python.exe app.py
```

Calling the virtual-environment Python directly also works when PowerShell
script activation is blocked by the Windows execution policy. The included
`bootstrap_all_subjects.bat` performs the status/bootstrap/status sequence.

After signing in with any active subject selected, Dashboard continuation must
resolve to `/curriculum/units/<unit_id>/lesson`. The status and bootstrap
commands use the same `EASYNMT_DB_PATH` / Railway volume / local
`instance\users.db` resolution as `python app.py`; repeated bootstrap runs
reuse owner-scoped published curricula and repair only missing deterministic
baseline rows. Without `--all-subjects`, the command keeps its original
Mathematics-only behavior for backward compatibility.

Set a local `SECRET_KEY` in `.env` if sessions should survive process restarts.
`OPENAI_API_KEY` and Google OAuth credentials are optional for the offline core.

Run the regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

## Production configuration

The Railway configuration runs one Gunicorn worker with four threads. Attach a
persistent volume and set at least:

```text
SECRET_KEY=<random value of at least 32 characters>
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=1
```

Optional integrations:

```text
OPENAI_API_KEY=<required for public Beta>
OPENAI_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_LESSON_MAX_OUTPUT_TOKENS=6500
OPENAI_DAILY_LIMIT=40
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
```

- `/health` is a process liveness check.
- `/ready` returns 200 only when all release-blocking local checks pass.
- Automatic SQLite backups are written to the persistent volume and verified.

See [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md), [OPENAI_SETUP.md](OPENAI_SETUP.md),
and [GOOGLE_AUTH_SETUP.md](GOOGLE_AUTH_SETUP.md) for integration details.
The AI engine boundary and extension guide are documented in
[easynmt_ai/README.md](easynmt_ai/README.md).
The production multi-subject taxonomies, curriculum lifecycle, and Task 3
handoff are documented in
[easynmt_ai/curriculum/README.md](easynmt_ai/curriculum/README.md).
Curriculum-unit state, unlocking, XP, replacement, authorization, and legacy
compatibility are documented in
[easynmt_core/progress/README.md](easynmt_core/progress/README.md).
The production lesson lifecycle, cache, completion evidence, and schema
rollback are documented in
[easynmt_core/lessons/README.md](easynmt_core/lessons/README.md).
The Task 3C.1 quiz contract, persistence, security boundaries, and next-stage
handoff are documented in
[easynmt_core/quizzes/README.md](easynmt_core/quizzes/README.md).
The production audit and remaining Beta work are in
[PRODUCTION_AUDIT_REPORT.md](PRODUCTION_AUDIT_REPORT.md).
