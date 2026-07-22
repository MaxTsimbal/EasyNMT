# Mentory v1.0.0-beta · Mobile & XP Polish

- Виправлено історичний баг, коли завершений урок відображався з `0 XP`. XP відновлюється лише з серверних доказів і ніколи не дублюється чи зменшується.
- Після curriculum-тесту сервер одразу оновлює XP у сесії для сторінок результату, кабінету та профілю.
- На телефоні кнопка «Почати тему» займає всю ширину картки, має стабільну висоту й більше не ламає текст.
- Мобільний hero став компактнішим: прибрано порожній декоративний блок під основною дією.
- На сторінці «Сьогодні» показуються лише три найближчі теми; повний маршрут відкривається через «Інші уроки».
- Task 5.1 Personal Focus і компактний маршрут включені в цю накопичувальну збірку.
- Додано регресійні тести для XP-repair, мобільної CTA та компактного маршруту.

# Mentory Task 5.1 · Personal Focus & Compact Route

- Dashboard now shows only the three nearest curriculum topics; the full route stays in “Інші уроки”.
- The three-topic window follows the learner: previous/current/next where possible, and the final three topics after route completion.
- Personal focus now uses up to five recent production quiz attempts, lost points by skill, question numbers, current mastery, and the next recommended action.
- The focus panel links directly to the latest detailed quiz review when evidence exists.
- English retakes continue to receive a fresh server-gradeable variant after each submitted attempt; refreshing an unfinished attempt preserves the same questions.
- Added four regression tests for the compact route and dashboard contract.

---

# Mentory v1.0.0-beta.1 · Task 5 Beta Readiness

- Додано release gate для SQLite, storage, backups, OpenAI, Google OAuth і single-worker runtime.
- `/health` повертає release metadata; `/ready` перевіряє реальну локальну готовність без зовнішніх API-викликів.
- Додано автоматичні verified SQLite hot backups із SHA-256 manifest і retention policy.
- Додано CLI `beta check`, `beta backup`, `beta verify-backup` і `beta smoke`.
- Кожна відповідь має `X-Request-ID` та `X-Mentory-Version`; 500-помилки можна зіставити з Railway logs.
- Railway Beta за замовчуванням вимагає OpenAI, persistent volume та один web worker.
- Production lesson fallback більше не маскує збій AI шаблонним уроком.
- Додано cumulative installer і ручний acceptance checklist.

---

# Mentory v1.0 Beta

Найбільше оновлення: автономна генерація програми, тем, повних уроків, тестів із 12 питань та AI-перевірка з частковими балами.

# Mentory Final Update Before Beta

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
- Підготовлено документацію до Mentory v1.0 Beta.

---

# Mentory Changelog

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

- Повністю перебудовано дизайн чату як окремий AI Workspace у стилі Mentory.
- Додано багаточатову історію з пошуком, перейменуванням, закріпленням, видаленням та експортом.
- Додано SSE endpoint `/api/tutor-chat/stream`, плавну потокову відповідь і зупинку генерації.
- Додано три режими відповіді: пояснення, коротко та практика.
- Додано slash-команди, повторну генерацію, feedback, копіювання повідомлень і code blocks.
- Додано Markdown, таблиці, код і LaTeX через MathJax.
- Повністю перероблено мобільний UX, drawer, keyboard docking і safe area.
- Чат підготовлено до Responses API, серверної пам’яті та OpenAI Vision.

## Easy Chat v1.2 Native Redesign

- Повністю перебудовано інтерфейс чату під візуальну мову Mentory: космічний фон, фірмові фіолетово-сині акценти, компактний AI-викладач і чиста структура.
- Прибрано повне перезавантаження сторінки під час відповідей. Додано окремий JSON endpoint `/api/tutor-chat`.
- Повернуто плавний друк відповіді, локальний стан «Easy думає» та кнопку зупинки.
- Додано адаптивну мобільну версію, коректну роботу з екранною клавіатурою та safe area.
- Додано збереження поточної розмови в браузері, очищення без перезавантаження і короткий контекст попередніх повідомлень для AI.
- Додано базове форматування відповідей: заголовки, списки, цитати, жирний текст, inline code та code blocks.
- Глобальний loader більше не запускається на сторінці чату.

# Mentory v0.9.9.9 — Welcome Experience Reliability

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

# Mentory v0.9.9.9

- Зафіксовано останню стабільну демо-збірку перед v1.0 Beta.
- Уніфіковано номер версії в інтерфейсі.
- Збережено Progress Foundation, авторизацію, одноразову діагностику та Easy Chat Fix 6.1.
- Підготовлено чисту основу для інтеграції OpenAI без зміни поточної навчальної логіки.

# Mentory v0.9.9 — Виправлення 4: Progress Foundation

- Додано історію спроб тестів із захистом від повторного POST і повторного XP.
- Одна тема дає максимум 60 XP: 10 XP за першу невдалу практику та ще 50 XP після першого успішного проходження, або 60 XP за проходження з першої спроби.
- Текстові відповіді тесту автоматично зберігаються як чернетка й відновлюються після оновлення сторінки.
- Додано відновлення незавершеного уроку або тесту з Dashboard.
- Збережено останній відкритий урок і останній результат окремо для кожного предмета.
- Прогрес, серія, XP і розблокування наступної теми синхронізуються з базою даних.
- Старі плани автоматично мігрують у таблицю прогресу без втрати даних.
- Результат тесту відновлюється після оновлення сторінки.
- Бібліотека та сторінка прогресу тепер поважають блокування тем.

# Mentory v0.9.9 — Виправлення 3

- Easy працює як окремий AI-помічник і отримує контекст теми лише після відкриття з уроку.
- Сповіщення автоматично зникають через 5 секунд, а таймер зупиняється під час наведення або фокусу.
- Кнопку повернення нагору відсунено від плаваючої кнопки Easy.
- Плаваюча кнопка Easy отримала ефект натискання та узгоджену анімацію.
- Стартова діагностика більше не запускається повторно після звичайного оновлення чи нового deployment.
- Для нових користувачів діагностика все ще обов’язкова один раз після завершення онбордингу.
- Посилено контраст тексту в покроковому поясненні на аркуші.

# Mentory v0.9.9 — Виправлення 2

- Вирівняно й перемальовано мобільну кнопку меню ☰.
- Космічний маршрут отримав суцільну лінію та динамічне заповнення за прогресом.
- Усі шість точок маршруту вміщуються на вузькому екрані без обрізання.
- Плаваючу кнопку Easy приховано на телефоні, бо чат уже є в нижній навігації.
- Авторизацію, базу даних, уроки та серверні маршрути не змінено.

# Mentory v0.9.9 — Виправлення 1 (Mobile UX Redesign)

- Верхня кнопка меню на мобільному відкриває навігацію кабінету.
- Прибрано дубльовану плаваючу круглу кнопку меню.
- Замінено книжку біля наступного уроку на фірмовий знак Mentory.
- Нижня навігація отримала чисті SVG-іконки, зокрема нормальну іконку профілю.
- Оновлено сторінку профілю та мобільні відступи.
- Прибрано із PNG-логотипів відокремлений синій графічний артефакт.
- Google Login, маршрути, база даних та навчальна логіка не змінювалися.

# Mentory v0.9.9.5 Foundation

- Стабілізовано Railway healthcheck: `/health` завжди перевіряє лише живий вебпроцес.
- Прибрано дубльовані маршрути `/health`.
- Додано `/ready`.
- Створено модульну основу `easynmt_core/` перед інтеграцією OpenAI у v1.0.
- Збережено сумісність із чинними сторінками, Dashboard, уроками, тестами та Google OAuth.

# Mentory v0.9.9.5 — Authentication Core

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

# Mentory v0.9.9

- Додано інтерактивний «розумний зошит» із покроковим поясненням на аркуші.
- Для завдань 9–12 учень розв’язує задачу на папері та завантажує фото.
- Додано AI-перевірку рукописного ходу розв’язання з частковими балами 0–3.
- Якщо є помилка, Mentory створює копію фото з рамкою, поясненням і правильним кроком.
- Фото зберігаються поза static у приватній папці та відкриваються лише власнику.
- Додано адаптивний вигляд зошита для ПК і телефона.


## v0.9.9 Desktop Humanization Hotfix

- Замінено безособові інфінітиви на природні звертання до учня: «Навчись», «Зрозумій», «Пройди».
- Переписано описи на головній сторінці простою людською мовою.
- Прибрано надмірні вертикальні проміжки між блоками головної сторінки на ПК.
- Кабінет на ПК став ширшим і трохи більшим; мобільний вигляд не змінено.
# Mentory v0.9.9 Stable — Повна хуманізація текстів

- Переписано інтерфейсні тексти у природному стилі українського репетитора.
- Додано живі звертання: «зверни увагу», «подивись», «перевір», «спробуй».
- Спрощено формулювання для учнів 12–16 років без втрати точності.
- Посилено правила голосу AI у `prompts.py`.
- Хуманізовано повідомлення тестів, результатів, уроків, навігації та досягнень.
- Дизайн, маршрути, база даних і логіка прогресу не змінювалися.

# Mentory v0.9.8.1 Stable — Dashboard & Lessons Fix

- Повністю перебудовано Dashboard без вузьких вертикальних карток.
- Головний блок, статистика, рівні та маршрут тепер мають стабільну сітку.
- На телефоні меню кабінету відкривається збоку, а чат Easy завжди доступний.
- Пояснення уроків розширено: теорія, алгоритм, формули, приклади, помилки та самоперевірка.
- Повний приклад тепер має 6 послідовних кроків без пропусків.
- Збережено тест із 12 питань і письмовими відповідями 5–12.
- Перевірено Python, Jinja-шаблони, Flask endpoints і ключові навчальні маршрути.

# Mentory v0.9.8.1 Stable — Humanized Learning Engine

- Додано послідовне відкриття тем: наступна відкривається після успішного тесту.
- Тест розширено до 12 питань і 24 балів.
- Питання 1–4 мають вибір відповіді; 5–8 — коротку письмову; 9–12 — повне розв’язання.
- Прохідний результат: 18/24.
- Додано часткові бали за правильні кроки у складних задачах.
- Пояснення перероблено під один повний покроковий приклад.
- Додано єдиний природний голос Easy у prompts.py.
- Оновлено тексти уроків, тестів, результатів і навігації.

# Mentory v0.9.7.6 Stable Horizontal Dashboard

- Привітання переміщене першим блоком зверху.
- Кожна секція кабінету займає всю доступну ширину.
- Внутрішній вміст секцій перебудований горизонтально.
- Ліва навігаційна панель збережена окремою колонкою.
- Верхня панель кабінету спрощена.

# Mentory v0.9.7.6 Compact Dashboard Hotfix

- Dashboard cards made compact on desktop.
- Mascot size constrained to prevent layout overflow.
- Statistics, roadmap, AI card, and lesson list no longer stretch vertically.
- Text wrapping and spacing improved.
- Mobile layout preserved.

# Mentory v0.9.7.6 Stable Hotfix

- Fixed dashboard 500 error caused by an incorrect Flask endpoint.
- Replaced `url_for("achievements")` with `url_for("achievements_page")`.
- Rechecked every `url_for()` reference in all templates against registered Flask endpoints.
- Verified Python syntax and core route responses with Flask test client.

# Mentory v0.9.7.6.2

- Dashboard navigation moved into a separate full-height desktop sidebar.
- Added grouped learning, tools, profile, and settings navigation.
- Preserved compact responsive navigation for tablets and phones.

# Mentory Changelog

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

# Mentory Changelog

## v0.9.6 Cosmic Tutor
- New cosmic background across landing, onboarding, authentication and dashboard.
- Mentory robot is now the main AI tutor and brand mascot.
- Compact goal, subject and date selection screens designed to fit without scrolling.
- New glass cards, responsive layout, micro-animations and space journey progress.
- Added logo assets and favicon.
- Preserved accounts, database, SEO, Google verification support and Railway deployment.


## v0.9.6 Cosmic Tutor

- Додано SEO title, description, canonical і social metadata.
- Додано фрази Mentory та «Легкий НМТ» у головну сторінку.
- Додано structured data для освітнього вебзастосунку.
- Додано динамічні `/robots.txt` і `/sitemap.xml`.
- Приватні сторінки захищено від індексації за замовчуванням.
- Додано підтримку Google Search Console verification через Railway Variable.
- Додано `SEO_SETUP.md`.

# Mentory Changelog

## v0.9.6 Cosmic Tutor Label Fix
- Updated the dashboard release badge from `v0.7.9 Beta Ready` to `v0.9.6 Cosmic Tutor`.
- Updated page metadata and internal release labels.
- Renamed the beta-readiness screen to a public-launch readiness screen.
- Prepared the build as the final local release before deployment.


## v0.9.1 UI Fix
- Відновлено горизонтальний індикатор кроків 1–2–3 на сторінках онбордингу.
- Повернуто окрему зміну предмета в особистий кабінет і профіль.
- Додано адаптивні стилі для мобільних екранів.
# Mentory Changelog

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
- Quiz mistakes are now stored in SQLite and remain visible after restarting Mentory.
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
