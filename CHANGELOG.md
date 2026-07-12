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

## v0.9.6 Cosmic Tutor Responsive — 2026-07-12
- Повний космічний редизайн головної сторінки.
- Новий responsive header і мобільне меню.
- Новий onboarding для цілі, предмета та часу без довгих сторінок.
- Новий glassmorphism Dashboard з AI-викладачем.
- Космічна шкала прогресу: Земля → Місяць → Орбіта → Марс → 190+ → 200.
- Адаптація під ПК, ноутбуки, планшети та смартфони.
- Оновлені анімації, прелоадер, FAQ, progress bars і accessibility.
