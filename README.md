# EasyNMT

EasyNMT is a Flask and SQLite learning platform for structured NMT preparation.
The active product path combines curated lessons, server-generated quizzes,
per-subject progress, mistake review, and an optional OpenAI-powered tutor.

This repository is a hardened v1.0 Beta candidate. The core learning flow works
without an OpenAI key; in that case the tutor exposes an explicit offline mode
and uses only curated lesson material.

## Architecture

- `app.py` — Flask routes, authentication, onboarding, lesson flow, quiz
  finalization, progress views, and API orchestration.
- `learning_engine.py` — canonical quiz construction and deterministic grading.
- `easynmt_ai/` — central AI orchestrator, shared context and models, independent
  engine contracts, prompt layer, cache boundary, conversation repository,
  attachment validation, and streaming support.
- `easynmt_core/health.py` — separate liveness and database-readiness endpoints.
- `easynmt_core/lessons/` — production curriculum lesson persistence, secure
  delivery evidence, rendering, and the Task 3A completion handoff.
- `templates/` and `static/` — server-rendered UI and browser behavior.
- `tests/` — security, quiz consistency, persistence, API, and route regression
  coverage.

`easynmt_core/progress/` owns server-authoritative curriculum-unit state,
deterministic prerequisite/checkpoint unlocking, mastery, XP compatibility,
audit events, and future-UI read models.

The production Lesson Engine turns an in-progress curriculum unit into a
complete structured lesson, validates educational sufficiency, and caches the
accepted artifact in SQLite. It uses one OpenAI request through the central
orchestrator and returns a clear 503 when neither OpenAI nor a valid cached
lesson is available. Legacy numeric lessons continue to work offline.

SQLite is authoritative for progress, quiz attempts, unlock state, AI history,
and quotas. Flask's signed session stores identity and lightweight navigation
state; it is not trusted as the source of XP or completion data.

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Set a local `SECRET_KEY` in `.env` if sessions should survive process restarts.
`OPENAI_API_KEY` and Google OAuth credentials are optional for the offline core.

Run the regression suite:

```powershell
python -m unittest discover -v
python -m pip check
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
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_LESSON_MAX_OUTPUT_TOKENS=6500
OPENAI_DAILY_LIMIT=40
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
```

- `/health` is a process liveness check.
- `/ready` returns 200 only when the SQLite database exists and is initialized.

See [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md), [OPENAI_SETUP.md](OPENAI_SETUP.md),
and [GOOGLE_AUTH_SETUP.md](GOOGLE_AUTH_SETUP.md) for integration details.
The AI engine boundary and extension guide are documented in
[easynmt_ai/README.md](easynmt_ai/README.md).
The production mathematics taxonomy, curriculum lifecycle, and Task 3 handoff
are documented in
[easynmt_ai/curriculum/README.md](easynmt_ai/curriculum/README.md).
Curriculum-unit state, unlocking, XP, replacement, authorization, and legacy
compatibility are documented in
[easynmt_core/progress/README.md](easynmt_core/progress/README.md).
The production lesson lifecycle, cache, completion evidence, schema rollback,
and Task 3C handoff are documented in
[easynmt_core/lessons/README.md](easynmt_core/lessons/README.md).
The production audit and remaining Beta work are in
[PRODUCTION_AUDIT_REPORT.md](PRODUCTION_AUDIT_REPORT.md).
