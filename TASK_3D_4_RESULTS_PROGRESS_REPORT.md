# Task 3D.4 — Results, XP & Progress Sync

## Goal

Make the production assessment a complete learning cycle rather than an isolated quiz page:

`lesson → assessment → result → XP → progress → next unit or focused retry`

## Implemented

### Complete-answer protection

- The server now requires non-empty answers for all 12 server-issued question IDs.
- Unknown client fields remain ignored.
- Incomplete finalization returns `422 quiz_answers_incomplete` with exact missing question numbers.
- Submitted work is saved as a draft and no attempt, score, XP, or progress mutation is created.

### Result metadata

Every persisted result now includes:

- attempt number;
- best score for the unit;
- whether this attempt is a new personal best;
- fully correct, partially correct, and incorrect question counts;
- points still needed to reach 18/24.

The metadata is computed from persisted attempts and review evidence, so refreshing an old result remains truthful.

### XP and progress guarantees

- Passing the required assessment completes the unit and recalculates unlocks atomically.
- The next eligible unit becomes available in the same transaction.
- XP remains one-time only.
- A repeated request for the same token returns the stored result without changing anything.
- Practice attempts remain available after completion but award `0 XP` and cannot reduce completed progress.

### Student-facing flow

- The finish button activates only after all 12 answers are present.
- Missing questions are highlighted and the page moves to the first missing answer.
- The final button enters a locked checking state to reduce duplicate submissions.
- Result pages show attempt score, best score, personal-best state, XP, and answer breakdown.
- Failed learners get a clear retry and lesson-review path.
- Passed learners get the next-topic action only when the progress engine has actually unlocked it.

## Verification

- `157` automated tests: OK
- `python -m compileall -q .`: OK
- Python AST parse of active modules: OK
- Inline quiz JavaScript syntax check with Node: OK
- `python -m pip check`: no broken requirements
