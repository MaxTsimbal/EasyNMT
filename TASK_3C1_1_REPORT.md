# Task 3C.1.1 Human Answer Grading Hotfix

This hotfix corrects the first deterministic quiz foundation after real learner testing.

## Fixed

- Replaced vague questions 11–12 with concrete tasks based on the lesson examples and mistakes.
- Reworded all written questions so the learner knows exactly what is expected.
- A correct final answer in questions 9–10 now earns 2/3 even without a long derivation.
- Short answers receive partial credit for a correct idea instead of requiring AI-like reference prose.
- Question 7 awards one point for identifying the mistake and one for fixing it.
- Question 8 accepts any correct rule or formula from the lesson.
- Added typo-tolerant and basic morphology-tolerant matching for Ukrainian and English.
- Moved long reference answers into a collapsed “show example” section.
- Existing submitted attempts remain immutable. New attempts use schema `quiz.v1.1-human`.
- Existing quiz rows are upgraded in place while old session snapshots remain unchanged.

## Security retained

- Scores remain server-authoritative.
- Attempt snapshots remain integrity-checked.
- XP and progress updates remain atomic and idempotent.
