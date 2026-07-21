# EasyNMT Changelog

## Task 3D — Production Exam Engine (2026-07-21)

- Rebuilt all 12 English curriculum assessments around practical exam exercises.
- Added seeded variants for all 12 English topics without breaking drafts on refresh or parallel tabs.
- Replaced rule-recall questions 5–8 with negation, questions, word order, correction, translation and reading tasks.
- Rebuilt questions 9–12 as three independently scored parts.
- Added `exact` and `rubric` grading modes with server-only answer keys.
- Added skill, reading context, placeholders and safe review metadata to the quiz contract.
- Upgraded Contextual Easy to exercise-aware help while guarding every rubric answer part.
- Added answered-progress navigation, compact exam cards and a personalized result practice plan.
- Removed the confusing dependency of question 12 on question 11.
- Preserved legacy snapshot readability and upgraded new quizzes to `quiz.v1.4-production-exam`.
- Verified the integrated project with 141 automated tests and 31 subtests.

## Task 3C.2 — Student Clarity Final (2026-07-20)

- Split every quiz item into a clear action, concrete task, and answer format.
- Added 225 reviewed fallback tasks covering all 75 published curriculum topics.
- Replaced abstract skill labels in questions 9–12 with actual exercises.
- Preserved partial-credit grading for correct results and natural-language answers.
- Passed the visible active question and answer format to Contextual Easy without exposing grading keys.
- Preserved Easy Chat v3.0.1 typing, smooth scrolling, stop control, and local loading state.
- Kept legacy quiz snapshots readable while upgrading new quiz content to `quiz.v1.3-student-clarity`.
- Added full curriculum coverage, public-payload, compatibility, UI, and Easy-context regression tests.

## Task 3C.1 — Production Quiz Foundation (2026-07-20)

- Added a production quiz for every completed curriculum lesson.
- Enforced the 12-question, 24-point, 18-point pass contract on the server.
- Added immutable quiz snapshots, attempt tokens, draft autosave, and result pages.
- Made grading, XP, completion, and next-unit unlocking atomic and idempotent.
- Prevented forged client scores, XP, pass state, and unknown question IDs.
- Added owner-scoped quiz APIs and hid internal answer keys from public payloads.
- Added 9 dedicated production quiz tests; the complete suite now passes 113 tests.
- Kept AI semantic grading and photo grading for later Task 3C stages.

# Task 3B.3 — Multi-Subject Production Lesson Platform

- Added one canonical subject registry for Mathematics, Ukrainian, History, and English.
- Added versioned, validated NMT taxonomies for every active subject.
- Generalized curriculum bootstrap and status reporting to all active subjects.
- Added `--all-subjects` and repeatable `--subject` CLI options while preserving the Mathematics default.
- Routed every published subject through the shared Production Lesson Engine and curriculum progress model.
- Added subject-aware prompt policy, validation, and deterministic offline recovery grounded in taxonomy metadata.
- Rejected invented topic IDs and stale/mismatched deterministic fallback requests.
- Added multi-subject idempotency, publication, Dashboard navigation, lesson rendering, cache, completion, and isolation coverage.
- Added `bootstrap_all_subjects.bat` for Windows systems where PowerShell script activation is blocked.

---

# EasyNMT v1.0 Beta

Найбільше оновлення: автономна генерація програми, тем, повних уроків, тестів із 12 питань та AI-перевірка з частковими балами.

# EasyNMT Final Update Before Beta

- Easy Chat перетворено на модуль **AI Викладач**.
- Додано єдиний OpenAI gateway на Responses API.
- Додано нативний SSE streaming для реальних deltas моделі.
- Додано серверні розмови, повідомлення, вкладення та feedback.
- Додано завантаження фото розв’язання з preview у composer.
- Додано навчальний контекст: предмет, ціль, прогрес, XP, серія, урок і слабкі теми.
- Додано API статусу та керування історією.
- Додано безпечний fallback без ключа.
- Централізовано також AI-перевірку фото: лише `easynmt_ai/service.py` імпортує OpenAI SDK.
- Серверна історія стала авторитетним джерелом контексту після синхронізації розмови.
- Додано перевірку справжнього формату зображень, денний upload-ліміт і видалення приватних файлів разом із розмовою.
- Додано міграцію AI-повідомлень із user-scoped ID для ізоляції акаунтів.
- Підготовлено документацію до EasyNMT v1.0 Beta.

---

# EasyNMT Changelog

## Easy Chat v3.0 Nebula Mobile-First

- Rebuilt the phone layout around a compact native-style workspace.
- Replaced the oversized mobile hero with a concise greeting and 2×2 action launcher.
- Reduced the mobile header to 56 px and tightened thread spacing.
- Rebuilt the composer as a single-row dock with a 16 px input to prevent iOS focus zoom.
- Added Visual Viewport keyboard tracking and safe-area handling for Safari and in-app browsers.
- Reworked rename/delete dialogs as centered desktop-style windows without scale animation.
- Added `interactive-widget=resizes-content` viewport support where browsers implement it.
- Preserved v2 local chat history, streaming, commands, export, rename, pin and feedback features.
- Added dedicated v3 CSS and JavaScript assets so the previous stable files remain available for rollback.

## Easy Chat v2.0 AI Workspace Foundation

- Повністю перебудовано дизайн чату як окремий AI Workspace у стилі EasyNMT.
- Додано багаточатову історію з пошуком, перейменуванням, закріпленням, видаленням та експортом.
- Додано SSE endpoint `/api/tutor-chat/stream`, плавну потокову відповідь і зупинку генерації.
- Додано три режими відповіді: пояснення, коротко та практика.
- Додано slash-команди, повторну генерацію, feedback, копіювання повідомлень і code blocks.
- Додано Markdown, таблиці, код і LaTeX через MathJax.
- Повністю перероблено мобільний UX, drawer, keyboard docking і safe area.
- Чат підготовлено до Responses API, серверної пам’яті та OpenAI Vision.

## Easy Chat v1.2 Native Redesign

- Повністю перебудовано інтерфейс чату під візуальну мову EasyNMT: космічний фон, фірмові фіолетово-сині акценти, компактний AI-викладач і чиста структура.
- Прибрано повне перезавантаження сторінки під час відповідей. Додано окремий JSON endpoint `/api/tutor-chat`.
- Повернуто плавний друк відповіді, локальний стан «Easy думає» та кнопку зупинки.
- Додано адаптивну мобільну версію, коректну роботу з екранною клавіатурою та safe area.
- Додано збереження поточної розмови в браузері, очищення без перезавантаження і короткий контекст попередніх повідомлень для AI.
- Додано базове форматування відповідей: заголовки, списки, цитати, жирний текст, inline code та code blocks.
- Глобальний loader більше не запускається на сторінці чату.

# EasyNMT v0.9.9.9 — Welcome Experience Reliability

- Welcome screen is now shown after email/Google login and after first page load in a new browser session.
- The redirect logic was moved from an ignored block in `dashboard.html` to the shared `base.html`.
- New users see the welcome screen after completing diagnostics.
- Added responsive subject-specific backgrounds for Mathematics, English, Ukrainian, and History using CSS and inline SVG only.
- Internal navigation does not reopen the welcome screen in the same browser session.


## v0.9.9.9 — Account and universal menu patch

- Cabinet sidebar is reused on all authenticated application sections.
- Profile settings include a visible sign-out action.
- Existing Google accounts with missing or partial legacy plans are repaired safely and sent directly to the dashboard.
- Brand-new Google accounts still complete onboarding once.

# EasyNMT v0.9.9.9

- Зафіксовано останню стабільну демо-збірку перед v1.0 Beta.
- Уніфіковано номер версії в інтерфейсі.
- Збережено Progress Foundation, авторизацію, одноразову діагностику та Easy Chat Fix 6.1.
- Підготовлено чисту основу для інтеграції OpenAI без зміни поточної навчальної логіки.

# EasyNMT v0.9.9 — Виправлення 4: Progress Foundation

- Додано історію спроб тестів із захистом від повторного POST і повторного XP.
- Одна тема дає максимум 60 XP: 10 XP за першу невдалу практику та ще 50 XP після першого успішного проходження, або 60 XP за проходження з першої спроби.
- Текстові відповіді тесту автоматично зберігаються як чернетка й відновлюються після оновлення сторінки.
- Додано відновлення незавершеного уроку або тесту з Dashboard.
- Збережено останній відкритий урок і останній результат окремо для кожного предмета.
- Прогрес, серія, XP і розблокування наступної теми синхронізуються з базою даних.
- Старі плани автоматично мігрують у таблицю прогресу без втрати даних.
- Результат тесту відновлюється після оновлення сторінки.
- Бібліотека та сторінка прогресу тепер поважають блокування тем.

# EasyNMT v0.9.9 — Виправлення 3

- Easy працює як окремий AI-помічник і отримує контекст теми лише після відкриття з уроку.
- Сповіщення автоматично зникають через 5 секунд, а таймер зупиняється під час наведення або фокусу.
- Кнопку повернення нагору відсунено від плаваючої кнопки Easy.
- Плаваюча кнопка Easy отримала ефект натискання та узгоджену анімацію.
- Стартова діагностика більше не запускається повторно після звичайного оновлення чи нового deployment.
- Для нових користувачів діагностика все ще обов’язкова один раз після завершення онбордингу.
- Посилено контраст тексту в покроковому поясненні на аркуші.

# EasyNMT v0.9.9 — Виправлення 2

- Вирівняно й перемальовано мобільну кнопку меню ☰.
- Космічний маршрут отримав суцільну лінію та динамічне заповнення за прогресом.
- Усі шість точок маршруту вміщуються на вузькому екрані без обрізання.
- Плаваючу кнопку Easy приховано на телефоні, бо чат уже є в нижній навігації.
- Авторизацію, базу даних, уроки та серверні маршрути не змінено.

# EasyNMT v0.9.9 — Виправлення 1 (Mobile UX Redesign)

- Верхня кнопка меню на мобільному відкриває навігацію кабінету.
- Прибрано дубльовану плаваючу круглу кнопку меню.
- Замінено книжку біля наступного уроку на фірмовий знак EasyNMT.
- Нижня навігація отримала чисті SVG-іконки, зокрема нормальну іконку профілю.
- Оновлено сторінку профілю та мобільні відступи.
- Прибрано із PNG-логотипів відокремлений синій графічний артефакт.
- Google Login, маршрути, база даних та навчальна логіка не змінювалися.

# EasyNMT v0.9.9.5 Foundation

- Стабілізовано Railway healthcheck: `/health` завжди перевіряє лише живий вебпроцес.
- Прибрано дубльовані маршрути `/health`.
- Додано `/ready`.
- Створено модульну основу `easynmt_core/` перед інтеграцією OpenAI у v1.0.
- Збережено сумісність із чинними сторінками, Dashboard, уроками, тестами та Google OAuth.

# EasyNMT v0.9.9.5 — Authentication Core

- Google OpenID Connect винесено в окремий `auth_service.py`.
- Додано незалежний маршрут `/health` для Railway Healthcheck.
- OAuth більше не може зламати запуск основного сайту.
- Callback завжди формується як HTTPS.
- Додано безпечну діагностику `/auth/google/status`.
- Додано режим «не виходити з акаунта».
- Секрети не виводяться в логи або інтерфейс.

## v0.9.9.5 — Google OAuth Reliability Fix

- Google OAuth now imports Authlib as a required dependency instead of silently disabling login.
- OAuth configuration is validated with safe logs that never print secret values.
- Callback URL is generated automatically from the Railway HTTPS host.
- Added `/auth/google/status` for safe deployment diagnostics.
- Added `cryptography` explicitly for OpenID Connect token validation.
- Technical environment-variable names are no longer shown to users.

# EasyNMT v0.9.9

- Додано інтерактивний «розумний зошит» із покроковим поясненням на аркуші.
- Для завдань 9–12 учень розв’язує задачу на папері та завантажує фото.
- Додано AI-перевірку рукописного ходу розв’язання з частковими балами 0–3.
- Якщо є помилка, EasyNMT створює копію фото з рамкою, поясненням і правильним кроком.
- Фото зберігаються поза static у приватній папці та відкриваються лише власнику.
- Додано адаптивний вигляд зошита для ПК і телефона.


## v0.9.9 Desktop Humanization Hotfix

- Замінено безособові інфінітиви на природні звертання до учня: «Навчись», «Зрозумій», «Пройди».
- Переписано описи на головній сторінці простою людською мовою.
- Прибрано надмірні вертикальні проміжки між блоками головної сторінки на ПК.
- Кабінет на ПК став ширшим і трохи більшим; мобільний вигляд не змінено.
# EasyNMT v0.9.9 Stable — Повна хуманізація текстів

- Переписано інтерфейсні тексти у природному стилі українського репетитора.
- Додано живі звертання: «зверни увагу», «подивись», «перевір», «спробуй».
- Спрощено формулювання для учнів 12–16 років без втрати точності.
- Посилено правила голосу AI у `prompts.py`.
- Хуманізовано повідомлення тестів, результатів, уроків, навігації та досягнень.
- Дизайн, маршрути, база даних і логіка прогресу не змінювалися.

# EasyNMT v0.9.8.1 Stable — Dashboard & Lessons Fix

- Повністю перебудовано Dashboard без вузьких вертикальних карток.
- Головний блок, статистика, рівні та маршрут тепер мають стабільну сітку.
- На телефоні меню кабінету відкривається збоку, а чат Easy завжди доступний.
- Пояснення уроків розширено: теорія, алгоритм, формули, приклади, помилки та самоперевірка.
- Повний приклад тепер має 6 послідовних кроків без пропусків.
- Збережено тест із 12 питань і письмовими відповідями 5–12.
- Перевірено Python, Jinja-шаблони, Flask endpoints і ключові навчальні маршрути.

# EasyNMT v0.9.8.1 Stable — Humanized Learning Engine

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

## v0.9.9 — AI Tutor Chat UI
- Повністю перероблено сторінку AI-репетитора у форматі сучасного повноекранного чату.
- Додано бічну панель, швидкі навчальні дії, адаптивне поле введення та мобільний режим.
- Поточну серверну логіку й демо-відповіді збережено без змін.

## v0.9.9.5 — Complete Learning Journey
- Added a five-question starting diagnostic for every subject.
- Added level-based recommendations and a personal focus block on the dashboard.
- Connected lesson reading to test access through a readiness checkpoint.
- Rebuilt the lesson page for complete beginners with theory, examples, mistakes, and self-checks.
- Added About, Pricing, and Privacy pages with footer navigation.

## v0.9.9.9 — Final Polish Pack (2026-07-18)

- Піднято кнопку «Почнемо» на Welcome Experience, щоб вона не притискалася до нижнього краю екрана.
- Замість порожнього синього кадру додано фірмову космічну сцену завантаження з роботом Easy, зорями, планетами та індикатором прогресу.
- Завантажувальна сцена тепер використовується також між сторінками під час мережевого переходу.
- На сторінках навчання в хедері залишено лише кнопку «Кабінет».
- «Можливості», «Предмети», «Як це працює» та «Вийти» перенесено в профіль і меню кабінету.
- Додано контекстний чат Easy безпосередньо на сторінці уроку: на ПК кнопка містить назву Easy та робота, на телефоні показується компактна іконка.
- Додано JSON endpoint `/api/lesson-chat`, який відповідає в контексті поточного уроку без переходу на окрему сторінку.
- Кнопку «Відкрити пояснення на аркуші» перетворено на великий акцентний блок.
- Мобільне меню кабінету примусово закривається після переходів, відновлення сторінки з кешу та нового відкриття сайту.

## v0.9.9.9 Ultimate Polish
- Removed the duplicate floating Easy launcher on phones and tablets.
- Kept Easy as a single permanent tab in the mobile bottom navigation.
- Improved iPhone safe-area spacing and bottom content clearance.
- Stabilized the desktop Easy launcher position.

## Easy Chat v1.1 Foundation
- Повністю перебудовано інтерфейс Easy Chat у форматі AI Workspace.
- Додано нову бокову панель, верхню панель, стартовий екран і картки швидких запитів.
- Перероблено повідомлення користувача й Easy, composer та мобільну адаптацію.
- Додано окремий ізольований stylesheet `easy_chat_v11.css` для безпечного розвитку наступних версій.
- Збережено чинні Flask-маршрути, POST-форми та AI-відповіді.

## Easy Chat v1.1.1 Continuity Hotfix
- Restored smooth character-by-character rendering of Easy answers.
- Replaced full-page chat POST reloads with in-place fetch updates.
- Disabled the global page loader for every Easy Chat form.
- Added a local three-dot thinking state while the AI response is generated.
- Preserved the v1.1 visual redesign and existing Flask tutor route.

## Easy Tutor Brain Humanization Hotfix
- Added a local zero-cost intent analyzer for explanation, solving, checking, practice and concise requests.
- Added detection of confusion and repeated failed explanations.
- Easy now changes explanation strategy instead of repeating the same answer.
- Improved natural Ukrainian tutor voice and removed canned chatbot openings/closings.
- Added smarter clarification behavior for genuinely ambiguous short prompts.
- Preserved lesson, progress, weak-topic and conversation context in every response.

## Task 3C v3.0.1 — Contextual Easy runtime fix

- Fixed the full-page transition loader being triggered by the contextual Easy composer.
- Connected the compact lesson/quiz assistant to the Easy Chat v3 markdown renderer.
- Added smooth auto-scroll, word-by-word typing, a stop action, and truthful online/offline status.
- Added a plain-text OpenAI retry when strict structured output is rejected, preventing silent template-only behavior.
- Made the deterministic quiz fallback use the active question and the most relevant lesson concept.
- Added UI and orchestration regression tests for the contextual assistant.
