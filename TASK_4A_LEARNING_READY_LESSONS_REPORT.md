# Task 4A — Learning-Ready Lesson Standard

## Goal

Turn production lessons into a real learning experience rather than a long page of theory:

`explanation → worked examples → independent practice → self-check → assessment`

## Implemented

### Guided practice contract

Every new lesson contains exactly three original tasks:

1. foundation;
2. guided;
3. exam.

Each task includes:

- a concrete prompt;
- a hint that does not directly reveal the answer;
- at least two solution steps;
- an expected answer;
- an explanation of why the method works;
- explicit references to the concepts taught in the lesson.

### Educational validation

The server rejects lesson output when:

- practice tasks are missing, duplicated, or out of order;
- a practice prompt copies a worked example;
- a hint, solution, answer, or explanation is incomplete;
- a task references an unknown concept;
- the three tasks do not rehearse every taught concept.

Invalid AI output is never persisted.

### Student-facing lesson experience

- Added a dedicated “Спробуй сам” section between practical tips and recap.
- Hints and full solutions are hidden inside accessible disclosure controls.
- The learner is explicitly asked to solve on paper before opening help.
- Practice cards adapt to one column on smaller screens.
- Reduced-motion preferences are respected.

### Lesson and assessment alignment

Guided practice is now included in `Lesson.for_quiz()`. Quiz generation and later AI grading/tutoring can use the exact tasks and reasoning the learner practiced, while the assessment blueprint continues to prohibit content outside the lesson.

### Safe rollout

- Prompt version: `lesson-production-1.1`
- Schema version: `lesson-structured-1.1`

The new generation identity creates fresh validated lessons without rewriting old immutable lesson records.

## Verification

- `160` automated tests: OK
- `python -m compileall -q .`: OK
- Full lesson/API/navigation regressions: OK
- Mobile and reduced-motion CSS included
