# Task 5.1 · Personal Focus & Compact Route

## Quiz variants

For the published English curriculum, each **new submitted attempt** receives a new deterministic, server-gradeable variant. The seed includes the learner, curriculum unit, and attempt number. Refreshing the page or opening a parallel tab reuses the same unfinished server snapshot, so questions do not change halfway through a test.

This is intentionally not a new OpenAI request for every retake. The system rotates reviewed task-bank material, keeps the answer key server-side, and remains gradeable even if OpenAI is unavailable.

## Personal focus

The dashboard focus now prioritizes real learning evidence:

1. Up to five recent production quiz attempts.
2. Lost points grouped by skill, weighted toward recent attempts.
3. Question numbers where the weakness appeared.
4. The latest score and curriculum topic.
5. The grader’s next step or review tip.
6. Current curriculum mastery when no recent mistake evidence exists.
7. Diagnostic/legacy data only as a safe fallback.

The panel links directly to the most recent quiz review when possible.

## Compact route

The dashboard renders three nearby topics rather than all twelve:

- start of route: 1, 2, 3;
- middle of route: previous, current, next;
- completed route: final three topics.

The full route remains available through **Інші уроки**.

## Verification

- 205 automated tests: OK.
- Python compileall: OK.
- Dashboard route regression tests: 4/4 OK.
