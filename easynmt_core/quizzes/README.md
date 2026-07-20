# Production Curriculum Quiz Engine

This package implements Task 3C.1, the server-authoritative quiz foundation for
published curriculum units.

## Contract

Every production quiz contains exactly 12 questions and 24 available points:

- questions 1-4: four-option choice, 1 point each;
- questions 5-8: short written answers, 2 points each;
- questions 9-12: extended written answers, 3 points each.

A score of 18/24 passes the assessment. The browser never decides the score,
pass state, XP, or next-unit unlock.

## Lifecycle

1. A learner starts a published curriculum unit.
2. The Production Lesson Engine delivers and records a complete lesson.
3. Lesson completion moves the unit to `assessment_required`.
4. `CurriculumQuizService.start_attempt` builds or reuses a validated quiz,
   stores an immutable server snapshot, and issues a random attempt token.
5. Draft autosave accepts only question identifiers from that server snapshot.
6. `submit_attempt` grades only server-known questions against the stored
   answer key.
7. The quiz attempt, assessment result, XP, curriculum completion, and unlock
   transition commit in one SQLite transaction.
8. Repeating the same submission returns the stored result without duplicate
   XP or progress events.

## Security boundaries

- Public quiz payloads exclude correct answers, accepted answers, and grading
  keywords.
- Attempt tokens are server-issued and owner-scoped.
- The stored quiz content is protected by a canonical SHA-256 content hash.
- Unknown fields such as `score`, `passed`, `xp`, or invented question IDs are
  ignored for grading.
- A learner cannot read or submit another learner's attempt.
- Database failures roll back the quiz attempt and progress mutation together.

## Persistence

`CurriculumQuizRepository.ensure_schema()` creates these tables:

- `curriculum_quizzes`
- `curriculum_quiz_sessions`
- `curriculum_quiz_attempts`
- `curriculum_quiz_drafts`

The repository uses the same authoritative SQLite database path as the rest of
the application. On Railway this must be stored on the persistent volume
mounted at `/app/instance`.

## Current grading scope

Task 3C.1 uses deterministic grading grounded in the structured lesson. It does
not yet use OpenAI or image analysis. Semantic AI grading, partial-credit
rubrics, and photo-based solutions belong to the next Task 3C stages.
