# Task 3C.1 Report: Production Quiz Foundation

## Status

Task 3C.1 is implemented as a production-safe, deterministic quiz foundation
for every published curriculum unit and all four active subjects.

## Delivered

- A strict 12-question, 24-point production quiz contract.
- Four choice questions worth 1 point each.
- Four short written questions worth 2 points each.
- Four extended written questions worth 3 points each.
- An 18/24 pass threshold controlled by the server.
- Quiz generation grounded only in the delivered structured lesson.
- Immutable server-side quiz snapshots and content hashes.
- Server-issued, owner-scoped attempt tokens.
- Draft autosave restricted to server-known question IDs.
- Server-authoritative grading that ignores browser-supplied score, XP, pass
  state, and unknown fields.
- Atomic persistence of attempt, assessment result, XP, completion, and next
  unit unlock.
- Idempotent duplicate submission protection.
- Safe practice retakes after completion without duplicate XP.
- HTML quiz and result pages plus JSON start/submit/result APIs.
- A direct transition from the completed production lesson to its production
  quiz.

## Routes

- `GET|POST /curriculum/units/<unit_id>/quiz`
- `POST /api/curriculum/units/<unit_id>/quiz/start`
- `POST /api/curriculum/units/<unit_id>/quiz/submit`
- `POST|DELETE /api/curriculum/units/<unit_id>/quiz-draft`
- `GET /curriculum/quiz/attempts/<attempt_id>/result`

## Database additions

- `curriculum_quizzes`
- `curriculum_quiz_sessions`
- `curriculum_quiz_attempts`
- `curriculum_quiz_drafts`

Schema creation is idempotent and runs during application startup. Existing
users, curricula, lessons, and progress remain in the same database.

## Verification

- All Python modules compile successfully.
- 113 automated tests pass.
- Tests cover the exact scoring contract, authorization, locked-unit behavior,
  hidden answer keys, forged client fields, idempotency, drafts, rollback,
  HTML routes, API routes, XP, completion, and unlock behavior.
- Existing Task 3A, Task 3B, security, OAuth, AI architecture, legacy quiz, and
  multi-subject regression tests remain green.

## Deliberately deferred

Task 3C.1 does not claim semantic AI grading or photo grading. The next stages
should add:

1. rubric-based partial credit for written answers;
2. OpenAI grading behind the central AI orchestrator;
3. photo upload and vision analysis for questions 9-12;
4. teacher-style feedback and mistake classification;
5. cost limits, retry policy, moderation, and human-review fallbacks.
