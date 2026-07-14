# EasyNMT v0.9.9 — Виправлення 4: Progress Foundation

Статус: внутрішня демо-версія. Progress Foundation готовий до фінального тестування перед OpenAI.

Перевірено локально:
- міграцію старої бази без втрати плану, XP і завершених уроків;
- збереження та відновлення чернеток тесту;
- захист від повторного POST і повторного XP;
- сценарії «прохід з першої спроби» та «невдала спроба → прохід»;
- розблокування наступного уроку;
- відновлення результату після оновлення сторінки;
- основні маршрути кабінету через Flask test client;
- усі Python, JavaScript і 30 Jinja-шаблонів.

# EasyNMT v0.9.9.5

## Implemented
- Flask application and Railway deployment structure
- Email and Google authentication
- Goal, subject, and preparation-time onboarding
- Subject diagnostic with beginner/foundation/confident levels
- Personalized dashboard recommendations based on diagnostic and saved mistakes
- Locked lesson progression
- Beginner-first lesson structure
- Lesson readiness checkpoint before tests
- 12-question tests and partial scoring
- Progress, XP, streaks, achievements, and mistake history
- Professional tutor chat interface
- About, pricing, and privacy pages

## Future AI stage
After OpenAI is connected, generated lessons, adaptive explanations, chat memory, and photo grading can use the same learning structure already present in the interface.
