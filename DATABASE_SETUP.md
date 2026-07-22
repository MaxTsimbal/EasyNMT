# Mentory database

Mentory automatically creates `instance/users.db` on first launch.

Stored data:
- registered accounts and secure password hashes;
- selected goal, subject and preparation time;
- XP, progress, streak and last activity;
- completed lessons and best quiz results;
- achievements;
- quiz mistakes;
- quiz attempts, server-side quiz sessions and answer drafts;
- per-subject progress and lesson readiness;
- AI conversations, messages, feedback and attachment metadata;
- daily OpenAI usage and upload limits.
- versioned AI curricula, canonical units, checkpoints and lifecycle events;
- curriculum-unit/checkpoint progress, mastery, server-verified assessment
  records, conservative topic credits and progress audit events.
- immutable production lessons, hashed lesson-delivery evidence and lesson
  lifecycle audit events.

## Updating an existing Mentory folder
To keep accounts from an older version, copy the old file:

`instance/users.db`

into the `instance` folder of this version before launch. The app will add missing tables automatically without deleting existing accounts.

Curriculum, curriculum-progress and curriculum-lesson repositories use
additive, repeatable schema creation during startup. Their foreign keys preserve owner/curriculum/unit
consistency, and existing legacy lesson/XP rows are not rewritten. Back up the
database before deploying any application upgrade as normal production
practice.

Task 3B adds `curriculum_lessons`, `curriculum_lesson_deliveries`, and
`curriculum_lesson_events`. These tables are independent of legacy lesson and
quiz tables. See `easynmt_core/lessons/README.md` for the exact rollback order
and the data-loss warning for generated artifacts.

Do not upload `users.db` publicly because it contains account data.
