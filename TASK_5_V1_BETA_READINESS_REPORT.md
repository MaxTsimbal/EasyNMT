# Task 5 · Mentory v1.0 Beta Readiness

Дата: 2026-07-21  
Версія: `1.0.0-beta.1`  
Гілка публікації: `codex/production-hardening`

## Мета

Закрити фінальний технічний етап перед ручною перевіркою реальним учнем. Task 5
не додає ще один навчальний режим. Він робить уже створений цикл урок → тест →
AI-перевірка → XP → наступна тема контрольованим, спостережуваним і придатним
для Beta на одному Railway-сервісі з SQLite Volume.

## Реалізовано

### 1. Єдиний Beta readiness gate

Новий модуль `easynmt_core/beta_readiness.py` перевіряє без зовнішніх мережевих
запитів:

- `PRAGMA quick_check` і `foreign_key_check` для SQLite;
- наявність ключових таблиць навчання, AI та прогресу;
- можливість запису на persistent storage і мінімальний вільний простір;
- наявність Railway Volume, коли він обов’язковий;
- свіжість і цілісність резервної копії;
- OpenAI key та маршрути моделей для письмової і photo-перевірки;
- повну або коректно вимкнену конфігурацію Google OAuth;
- `DEBUG=0`, secure cookies і рівно один web worker для SQLite.

`/health` лишився легкою liveness-перевіркою. `/ready` тепер повертає 200 лише
коли немає release-blocking помилок. Він не викликає OpenAI або Google і не
публікує секрети.

### 2. Перевірені SQLite backups

Додано `SQLiteBackupManager`:

- створює консистентну hot backup через SQLite Backup API;
- перевіряє копію через `quick_check`, required tables і foreign keys;
- рахує SHA-256;
- записує JSON manifest;
- зберігає копії на Railway Volume;
- видаляє старі копії за retention policy;
- використовує lock-файл проти паралельного startup backup;
- не зупиняє вебпроцес при помилці backup, але readiness показує проблему.

За замовчуванням backup створюється не частіше одного разу на 24 години,
зберігаються останні 7 копій.

### 3. Команди для релізу

Додано Flask CLI:

```text
flask --app app beta check
flask --app app beta check --strict
flask --app app beta backup --reason before-release
flask --app app beta verify-backup <path>
flask --app app beta smoke
```

`beta check` показує PASS/WARN/FAIL без секретів. `beta smoke` перевіряє
`/health`, `/ready`, головну, реєстрацію та статус Google login через Flask.

### 4. Діагностика публічних помилок

Кожен HTTP response отримує:

- `X-Request-ID`;
- `X-Mentory-Version: 1.0.0-beta.1`.

Коректний вхідний request ID зберігається, небезпечний замінюється. Для 500
користувач бачить код запиту, а сервер записує той самий код у log. Це дозволяє
зіставити скрін учня з конкретною помилкою Railway.

### 5. Production-safe defaults

- Railway Beta вимагає OpenAI та persistent volume, якщо це явно не вимкнено.
- `WEB_CONCURRENCY=1` контролюється readiness, бо SQLite не підтримує поточну
  архітектуру з кількома репліками.
- deterministic lesson fallback локально доступний, але у Railway за
  замовчуванням вимкнений, щоб AI-збій не маскувався шаблонним уроком.
- Footer і health payload використовують одну release version.

## Межі перевірки

Автоматично перевірено код, SQLite, маршрути й fallback-сценарії. Реальні
OpenAI responses, реальний Google authorization-code exchange, поведінка
конкретного Railway Volume після redeploy і реальна камера телефона не можуть
бути чесно підтверджені без production credentials та ручного проходження.
Для цього додано `BETA_MANUAL_TEST_CHECKLIST.md`.

## Результат

Task 5 формує cumulative збірку від Task 3D.4 до Task 5. Після її deployment
можна переходити не до нового модуля, а до ручного acceptance test сайту як
звичайний учень. Знайдені під час нього дефекти мають оформлюватися як Beta
hotfixes із request ID та точним кроком відтворення.

## Автоматична перевірка збірки

Фінальна локальна перевірка Task 5:

- **201 automated tests: OK**;
- Python `compileall`: OK;
- AST parse: **87 Python files**;
- JavaScript syntax: **9 files**, OK;
- `pip check`: no broken requirements;
- production-like `beta check --strict`: 6/6 checks PASS;
- production-like `beta smoke`: `/health`, `/ready`, `/`, `/register` і
  `/auth/google/status` повернули 200.

Production-like перевірка використовувала тимчасову SQLite базу та фіктивні
значення credentials лише для локальної перевірки конфігураційного gate. Вона
не виконувала зовнішніх запитів і не є підтвердженням реальних OpenAI/Google
credentials.
