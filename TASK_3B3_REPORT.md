# Task 3B.3 — Multi-Subject Production Lesson Platform

## Реалізовано

- Єдиний canonical subject registry для чотирьох активних предметів.
- Production curricula для математики, української мови, історії України та англійської мови.
- Subject-aware Lesson Engine, промпти, валідація та deterministic fallback.
- Мультипредметний idempotent bootstrap із збереженням користувачів, XP та прогресу.
- Окрема ізоляція curriculum/progress за користувачем і предметом.
- Dashboard, Today, Library і Planner працюють через production curriculum unit IDs.
- Legacy `/lesson/<id>` збережено лише для справжньої сумісності без applicable published curriculum.
- Додано Windows helper `bootstrap_all_subjects.bat`.

## Активні предмети

| Ключ | Предмет | Тем у повній taxonomy |
|---|---|---:|
| `math` | Математика | 39 |
| `ukrainian` | Українська мова | 12 |
| `history` | Історія України | 12 |
| `english` | Англійська мова | 12 |

Фактична кількість одиниць у curriculum конкретного учня може бути меншою через його цільовий бал і progression policy.

## Перевірено

- Full pytest: **104 passed, 27 subtests passed**
- Python compilation: passed
- `pip check`: no broken requirements
- `/health`: HTTP 200
- `/ready`: HTTP 200
- SQLite integrity: `ok`
- Foreign-key violations: `0`
- Повторний all-subject bootstrap: idempotent
- Реальний Dashboard route для кожного предмета веде на `/curriculum/units/<unit_id>/lesson`
- У кожному предметі рендеряться всі 9 секцій
- Cache reuse перевірено
- Completion token і idempotent retry перевірено для всіх чотирьох предметів

## Межі цього оновлення

Task 3C не реалізований. Після production-уроку стан коректно переходить у `assessment_required`, але мультипредметний Production Quiz Engine ще потрібно створити.

Архів не містить `.env`, особистої `instance/users.db`, `.venv`, кешів або завантажень користувачів.
