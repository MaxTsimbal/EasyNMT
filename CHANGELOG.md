# EasyNMT v0.9.8 Stable — Humanized Learning Engine

- Додано послідовне відкриття тем: наступна відкривається після успішного тесту.
- Тест розширено до 12 питань і 24 балів.
- Питання 1–4 мають вибір відповіді; 5–8 — коротку письмову; 9–12 — повне розв’язання.
- Прохідний результат: 18/24.
- Додано часткові бали за правильні кроки у складних задачах.
- Пояснення перероблено під один повний покроковий приклад.
- Додано єдиний природний голос Easy у prompts.py.
- Оновлено тексти уроків, тестів, результатів і навігації.

# EasyNMT v0.9.7.6 Stable Horizontal Dashboard

- Привітання переміщене першим блоком зверху.
- Кожна секція кабінету займає всю доступну ширину.
- Внутрішній вміст секцій перебудований горизонтально.
- Ліва навігаційна панель збережена окремою колонкою.
- Верхня панель кабінету спрощена.

# EasyNMT v0.9.7.6 Compact Dashboard Hotfix

- Dashboard cards made compact on desktop.
- Mascot size constrained to prevent layout overflow.
- Statistics, roadmap, AI card, and lesson list no longer stretch vertically.
- Text wrapping and spacing improved.
- Mobile layout preserved.

# EasyNMT v0.9.7.6 Stable Hotfix

- Fixed dashboard 500 error caused by an incorrect Flask endpoint.
- Replaced `url_for("achievements")` with `url_for("achievements_page")`.
- Rechecked every `url_for()` reference in all templates against registered Flask endpoints.
- Verified Python syntax and core route responses with Flask test client.

# EasyNMT v0.9.7.6.2

- Dashboard navigation moved into a separate full-height desktop sidebar.
- Added grouped learning, tools, profile, and settings navigation.
- Preserved compact responsive navigation for tablets and phones.

# EasyNMT Changelog

## v0.9.7.6.1 Stable — Dashboard repair and stability pass
- Fixed the `/dashboard` 500 error caused by an invalid Jinja endpoint name.
- Replaced `url_for("progress")` with the real Flask endpoint `url_for("progress_page")`.
- Verified every template `url_for()` target against the Flask URL map.
- Added a full authenticated route smoke test for the main cabinet pages.
- Preserved the responsive mobile layout and desktop spacing hotfixes.


## v0.9.6.1 — Responsive layout hotfix
- Compact sticky navigation header.
- Removed legacy container padding from the header.
- Prevented hero text and AI tutor cards from overlapping.
- Improved tablet and smartphone hero layout.

# EasyNMT Changelog

## v0.9.6 Cosmic Tutor
- New cosmic background across landing, onboarding, authentication and dashboard.
- EasyNMT robot is now the main AI tutor and brand mascot.
- Compact goal, subject and date selection screens designed to fit without scrolling.
- New glass cards, responsive layout, micro-animations and space journey progress.
- Added logo assets and favicon.
- Preserved accounts, database, SEO, Google verification support and Railway deployment.


## v0.9.6 Cosmic Tutor

- Додано SEO title, description, canonical і social metadata.
- Додано фрази EasyNMT та «Легкий НМТ» у головну сторінку.
- Додано structured data для освітнього вебзастосунку.
- Додано динамічні `/robots.txt` і `/sitemap.xml`.
- Приватні сторінки захищено від індексації за замовчуванням.
- Додано підтримку Google Search Console verification через Railway Variable.
- Додано `SEO_SETUP.md`.

# EasyNMT Changelog

## v0.9.6 Cosmic Tutor Label Fix
- Updated the dashboard release badge from `v0.7.9 Beta Ready` to `v0.9.6 Cosmic Tutor`.
- Updated page metadata and internal release labels.
- Renamed the beta-readiness screen to a public-launch readiness screen.
- Prepared the build as the final local release before deployment.


## v0.9.1 UI Fix
- Відновлено горизонтальний індикатор кроків 1–2–3 на сторінках онбордингу.
- Повернуто окрему зміну предмета в особистий кабінет і профіль.
- Додано адаптивні стилі для мобільних екранів.
# EasyNMT Changelog

## v0.9 OpenAI Ready
- Додано окремий `ai_service.py` на OpenAI Responses API.
- Додано автоматичний демо-режим без API-ключа.
- Додано денний ліміт AI-запитів на користувача.
- Додано обмеження довжини питання та відповіді.
- Додано безпечні `.env.example` і `.gitignore`.
- Додано обробку помилок API без падіння сайту.
- На сторінці Easy-помічника показується активний режим і використаний ліміт.
- Оновлено залежності та інструкцію встановлення.

## v0.8 Stable
- Стабільна основа Flask, акаунти, прогрес, уроки, тести та досягнення.

## v0.9.2 Persistent Accounts & Progress
- SQLite path is now absolute, so the same database is used after every restart.
- Login sessions remain active for up to 30 days.
- Accounts, selected plan, XP, streak and progress are restored after login.
- Added separate progress storage for every subject.
- Switching subjects no longer deletes XP or completed lessons from the previous subject.
- Quiz mistakes are now stored in SQLite and remain visible after restarting EasyNMT.
- Added automatic database migrations for existing installations.


## v0.9.3 Public Deployment Ready
- Додано production-запуск через Gunicorn.
- Додано Railway-конфігурацію та health check.
- SQLite підключено до постійного Railway Volume.
- Посилено cookie та production-налаштування.
- Локальні бази й секрети виключено з Git.
