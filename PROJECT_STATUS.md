# EasyNMT v1.0 Beta

Статус: **готово до початку інтеграції EasyNMT v1.0 Beta**.

- чат перейменовано й переосмислено як **AI Викладач**;
- додано модульний пакет `easynmt_ai`;
- Responses API із нативним streaming підготовлено;
- серверна пам’ять розмов і повідомлень працює;
- фото розв’язань завантажуються через окремий безпечний endpoint;
- модель отримує навчальний контекст EasyNMT, а не лише текст чату;
- без ключа зберігається стабільний демо-режим;
- наступна версія: **EasyNMT v1.0 Beta**.

Деталі: `FINAL_UPDATE_BEFORE_BETA.md` та `OPENAI_INTEGRATION_MAP.md`.

---

# EasyNMT v1.0 Beta + Easy Chat v3.0 Nebula

Поточний чат: Easy Chat v3.0 Nebula Mobile-First готовий до перевірки на Railway. Після fix pack переходимо до OpenAI Responses API.

- новий дизайн і мобільний UX готові;
- streaming transport через SSE готовий;
- локальна багаточатова історія готова;
- Responses API, серверна пам’ять і Vision залишаються наступним етапом.

---

# EasyNMT v1.0 Beta

Остання стабільна демонстраційна збірка перед інтеграцією OpenAI та запуском v1.0 Beta.

## Статус

- Google та email авторизація підготовлені.
- Онбординг і одноразова діагностика працюють.
- Уроки, 12-питальні тести, результати, XP і розблокування рівнів працюють.
- Easy Chat має фінальний перед-AI інтерфейс і видиме поле введення на ПК та мобільному.
- Прогрес і чернетки тестів зберігаються в базі.
- OpenAI ще не є обов’язковою частиною цієї збірки.

## Наступний етап

EasyNMT v1.0 Beta: Responses API, AI-перевірка письмових відповідей, персональна пам’ять, AI-уроки й AI-тести.

---

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
- Subject-aware Welcome Experience is active after login and on a new browser session.
