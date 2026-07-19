# EasyNMT production audit

Date: 2026-07-19

Branch: `codex/production-hardening`

Baseline: `31f4e19` (`main`)
Scope: canonical repository `EasyNMT_Public`

## Executive status

The core EasyNMT learning journey is now internally consistent and suitable for
a controlled v1.0 Beta: account creation/login, signed sessions, onboarding,
diagnostics, lesson gating, quiz completion, XP/progress persistence, mistake
review, offline tutor behavior, and the active APIs have automated coverage.

This is not an unconditional production sign-off. Live Google OAuth, live
OpenAI calls, Railway volume behavior, backup/restore, and real traffic must be
validated in a staging deployment with the actual credentials and domain.

## Architecture reviewed

The application is a server-rendered Flask monolith backed by one SQLite
database. `app.py` owns routes and the learning workflow; quiz content and
deterministic grading live in `learning_engine.py`; the `easynmt_ai` package owns
the single OpenAI gateway, tutor orchestration, attachments, and AI persistence.
Static JavaScript enhances server-rendered pages but does not own authoritative
learning state.

The audit also found multiple repository copies outside the canonical nested
repository (`EasyNMT_Main`, a public backup, and archives). They were not edited
because they have separate history and may be user backups. All code changes in
this report apply only to `EasyNMT_Public`.

## Problems found

### Authentication and sessions

- Production accepted a missing, placeholder, or weak session secret.
- Proxy headers and secure cookies were not constrained tightly enough to the
  Railway environment.
- Unsafe form and JSON mutations had no universal CSRF protection.
- Login retained pre-authentication session data, enabling session fixation.
- A stale signed session could rebind identity using an email address.
- Login had no brute-force throttle and performed insufficient input bounds.
- Email uniqueness checks were case-sensitive at the database boundary.
- Several state changes, including logout and onboarding choices, were exposed
  as GET routes.
- Google provider failures logged response bodies that were unnecessary for
  diagnostics.

### Progress, unlocking, and quiz completion

- `/start` was a destructive GET route that reset learning progress.
- Locked lesson theory/examples were directly reachable, and readiness could be
  marked for locked lessons.
- Invalid lesson IDs were silently normalized to lesson 1 in multiple paths.
- Client-supplied repeated `question_ids` could turn one correct answer into a
  forged 24/24 result.
- Quiz writes were split across multiple commits. A mid-request failure could
  leave attempts, mistakes, XP, streak, and completion out of sync.
- Re-submission and parallel tabs could award inconsistent XP or invalidate each
  other.
- Client cookie state could overwrite newer database XP/progress from another
  tab or login session.
- Written answers received full credit based mainly on word count.
- Drafts accepted arbitrary keys and answer bodies were not server-capped.
- Photo uploads trusted file metadata more than file contents.

### AI and API behavior

- Missing OpenAI configuration was described as a “demo” mode even when no
  generative capability existed; `vision_ready` was always true.
- The general offline tutor produced generic invented-looking answers instead
  of clearly declaring the provider unavailable.
- AI request and attachment limits used check-then-write logic and could be
  exceeded by parallel requests.
- Unknown attachment IDs were silently ignored.
- Conversation update/delete endpoints reported success for missing records.
- Conversation deletion could leave message feedback and stored attachment
  files behind.
- Old server history queries could return the earliest messages rather than the
  latest messages.
- Streaming repository errors could terminate an SSE response without a final
  event.
- A disconnected `/v1-beta` generated-curriculum API had a separate data model,
  did not participate in real unlock/progress rules, exposed exception strings,
  contained ownership gaps, and returned 500 when OpenAI was absent.
- `/beta-check` was a hard-coded page that asserted system health without
  checking the running system.

### Error handling, health, and maintainability

- There was no generic HTML/JSON 500 response.
- `/ready` always returned ready without checking SQLite.
- There were no automated tests in the baseline.
- The repository contained a duplicate AI facade, a duplicate prompt module,
  empty modularization placeholders, superseded chat implementations, unused
  templates/assets, and many obsolete release snapshot documents.
- `static/css/style.css` is a large chronological accumulation of legacy UI
  overrides, and `app.py` remains a large monolith.

## Fixes applied

### Security and authentication

- Added fail-fast production secret validation (minimum 32 characters), secure
  production cookies, HttpOnly/SameSite settings, controlled proxy trust, and
  security/no-store response headers.
- Added signed-session CSRF tokens for all unsafe form and same-origin JSON/API
  requests. Converted logout and onboarding mutations to POST-only routes.
- Rotated the entire session on login and removed stale email-based identity
  recovery.
- Added bounded email/name/password validation, a case-insensitive unique email
  index, constant-cost invalid-password checking, and an 8-attempt/15-minute
  login throttle keyed by email and client address.
- Kept Google OAuth state and PKCE verification, required verified Google email,
  tested account linking, and stopped logging provider response bodies.

### Learning and persistence

- Removed the destructive `/start` route and made SQLite authoritative for
  progress/XP/streak reads and writes.
- Enforced valid and unlocked lessons for lessons, theory, examples, readiness,
  quizzes, drafts, and lesson-context AI routes.
- Made quiz finalization one `BEGIN IMMEDIATE` transaction covering the attempt,
  mistakes, completion, XP, streak, per-subject progress, legacy plan mirror,
  achievements, and cleanup of the server quiz session/draft.
- Made attempt tokens idempotent, retained parallel quiz sessions for one day,
  and preserved the intended maximum of 60 XP per lesson across fail-then-pass.
- Grades now iterate the server-stored canonical 12-question quiz; client
  `question_ids` cannot change score or total.
- Replaced word-count grading with exact, keyword/rubric, and evidence-overlap
  checks. Capped submitted and draft answer content.
- Validated uploads with Pillow, size/type/dimension checks, and user-scoped
  filenames before grading or serving them.

### AI, APIs, database, and errors

- Replaced “demo” with truthful `offline` mode throughout backend and UI.
  Offline general chat declares the provider unavailable; lesson chat uses
  curated lesson context.
- Consolidated all model configuration and calls through
  `OpenAIResponsesProvider`; removed the duplicate compatibility facade.
- AI usage is claimed atomically before an outbound request. Attachment quota
  check and metadata insert now share one write transaction.
- Missing attachments, invalid conversation updates, and missing user-owned
  records return explicit 400/404 responses.
- Conversation deletion is user-scoped and transactional, removes feedback,
  messages, metadata, and stored files. Abandoned unattached AI uploads are
  pruned after 24 hours.
- History returns the latest bounded messages in chronological display order.
- Added safe SSE fallback/final events, generic 500 handling, JSON-aware error
  responses, distinct liveness/readiness endpoints, and database readiness
  checks.
- Removed the disconnected generated-curriculum and beta-check surfaces rather
  than merging unverified generated content into the real learning model.
- Removed 7,700+ lines of superseded chat bundles, dead scaffolding, duplicate
  prompts/facades, unused templates/assets, and obsolete snapshot documents.

## Verification evidence

- `python -m unittest discover -v`: **22 tests passed**.
- Covered CSRF, session rotation, weak production secret rejection, login
  throttling, registration validation, Google PKCE/state, verified-email
  linking, offline AI, atomic AI quota, attachment cleanup, route smoke,
  locked lessons, score tampering, transaction rollback, idempotency, parallel
  quiz sessions, fail/pass XP, and progress persistence after re-login.
- All active Python modules passed `compileall`.
- All active JavaScript bundles passed `node --check`.
- `pip check`: no broken requirements.
- Fresh SQLite: `integrity_check=ok`, 0 foreign-key violations, 17 active tables.
- A real Flask process returned 200 for `/health`, `/ready`, `/`, `/register`,
  and `/auth/google/status` against a fresh database.
- Browser-rendered landing/registration pages loaded successfully, the loader
  cleared, CSRF metadata was present, and the browser console had no errors.

## Remaining issues

- Live OpenAI responses/streaming/photo grading were not exercised because no
  production key was used. Provider/model behavior and cost need staging tests.
- Live Google authorization-code exchange was not exercised against the real
  Google project/domain. The local callback logic, state, PKCE, verified email,
  and linking paths are covered with controlled tests.
- SQLite with one Gunicorn worker and WAL is appropriate for the planned Beta,
  but it is not a horizontal-scaling design. Multiple app replicas sharing a
  volume are not supported.
- Schema evolution still uses startup `CREATE/ALTER` logic rather than a
  versioned migration tool. Existing databases may retain tables from the
  removed generated-learning experiment; they are intentionally not dropped
  automatically because that would destroy data.
- Local email accounts have no email-verification, password-reset, account
  deletion, or formal data-export workflow.
- Solution-photo files referenced by historical quiz reviews have no retention
  policy or administrative cleanup job.
- `app.py` and `static/css/style.css` remain large. Static analysis found many
  likely legacy CSS selectors, but they were not bulk-deleted because the user
  explicitly requested no UI redesign and selector removal requires visual
  regression coverage across responsive/authenticated pages.
- Backup/archive copies outside the canonical repository can drift and should
  not be deployed.

## Recommendations for v1.0 Beta

1. Deploy this branch to a private staging Railway service with a fresh volume,
   strong secret, production domain, and restricted test credentials.
2. Run one real Google login/linking test and a small OpenAI test matrix covering
   text, SSE, image grading, quota exhaustion, provider timeout, and invalid key.
3. Add automated SQLite backups plus a documented restore drill before inviting
   students. Verify the backup includes both the database and upload folders.
4. Add local-email verification, password reset, account deletion/export, and a
   documented retention policy before a broad public Beta.
5. Introduce versioned migrations before the next schema change; archive old
   generated-learning tables only after a reviewed backup.
6. Add browser E2E coverage for registration → onboarding → diagnostic → lesson
   → ready → quiz → result → re-login, including mobile viewport screenshots.
7. Keep one deployment source of truth. Mark the outer backups/archives as
   non-deployable or move them outside the active workspace.
8. After behavior is locked with visual tests, split `app.py` by domain and
   consolidate `style.css` without changing the current UI.

## Commits

- `de7c984` — harden authentication and session mutations
- `afa043a` — make quiz completion atomic and tamper-resistant
- `fa20696` — harden AI usage and persistence
- `c9fcb95` — consolidate production code paths
- `9e0ed78` — remove superseded demo artifacts
- `b9b2673` — clean up abandoned AI attachments

The README/report commit is intentionally separate from the behavioral fixes.
