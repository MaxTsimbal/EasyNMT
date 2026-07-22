# Task 3D.2 Lesson Generation Loader

This package is installed over the current Mentory `codex/production-hardening` worktree.

## What is replaced

- `templates/base.html`
- `static/js/page_transitions.js`
- `static/css/style.css`
- `tests/test_lesson_generation_loader.py`
- `CHANGELOG.md`

The package does not include `.env`, SQLite databases, Railway secrets, `.git`, or the virtual environment.

## Public deployment

Use the same overlay installation flow as Task 3D.1, run the complete `unittest` suite, commit, and push to `codex/production-hardening`. Railway will deploy from GitHub.

## Browser verification

1. Open Dashboard, Today, Library, or Planner.
2. Start or continue a curriculum lesson that is not cached.
3. Confirm the full-screen scene appears immediately.
4. Confirm the topic, three stages, progress line, and 20–30 second message are visible.
5. Confirm the lesson opens automatically when generation finishes.
