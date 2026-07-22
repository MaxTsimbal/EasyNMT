# Підключення OpenAI до Mentory

## 1. Встановлення

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Локальні змінні

1. Скопіюй `.env.example` у `.env`.
2. Встав ключ після `OPENAI_API_KEY=`.
3. Не коміть `.env` і не надсилай його іншим.

## 3. Railway

У Railway відкрий **Variables** і додай щонайменше:

```text
OPENAI_API_KEY=твій_ключ
OPENAI_MODEL=gpt-4o-mini
OPENAI_TUTOR_FAST_MODEL=gpt-4o-mini
OPENAI_TUTOR_MODEL=gpt-4o-mini
OPENAI_TUTOR_REASONING_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_DAILY_LIMIT=40
OPENAI_STORE_RESPONSES=0
AI_DAILY_UPLOAD_LIMIT=20
```

## 4. Перевірка

Після деплою відкрий:

```text
/api/ai/status
```

Після входу має бути:
- `enabled: true`, якщо ключ працює;
- `streaming: true`;
- `vision_ready: true`;
- `server_memory: true`.

Без ключа платформа не падає. AI Викладач переходить в офлайн-режим і
використовує лише перевірені матеріали відкритого уроку. Загальний чат чесно
повідомляє, що зовнішній AI недоступний.


## Розумна маршрутизація Easy

Task 4B розділяє запити на чотири профілі: `fast`, `balanced`, `deep` і
`vision`. За замовчуванням усі використовують `OPENAI_MODEL`, тому після
оновлення витрати не змінюються автоматично.

- `OPENAI_TUTOR_FAST_MODEL` — короткі й прості запити;
- `OPENAI_TUTOR_MODEL` — звичайні навчальні пояснення;
- `OPENAI_TUTOR_REASONING_MODEL` — складні задачі й перевірка розв’язань;
- `OPENAI_VISION_MODEL` — запити із фото.

Сильнішу модель варто спочатку підключати лише до reasoning-профілю та
перевірити реальні витрати. Для моделей, які підтримують reasoning-контролі,
Easy автоматично передає потрібну глибину міркування і докладність відповіді.
Для інших моделей ці параметри не надсилаються.

## Навчальна пам’ять

SQLite зберігає лише прямі педагогічні побажання учня: коротко, простіше,
покроково, з підказками або детально. Бали, XP і відкриття тем як і раніше
контролює тільки серверна логіка Mentory.

## Контроль витрат

- денний ліміт задає `OPENAI_DAILY_LIMIT`;
- ліміт резервується атомарно перед зовнішнім викликом, тому паралельні запити
  не можуть перевищити його;
- довжину відповіді обмежує `OPENAI_MAX_OUTPUT_TOKENS`;
- максимум фото в одному запиті задає `AI_MAX_ATTACHMENTS`, розмір — `AI_MAX_ATTACHMENT_BYTES`, денний ліміт — `AI_DAILY_UPLOAD_LIMIT`;
- усі виклики проходять через `easynmt_ai/orchestrator.py`.

## Фото

AI Викладач приймає PNG, JPG, JPEG і WEBP до 5 МБ. Фото зберігаються у `RAILWAY_VOLUME_MOUNT_PATH/ai_uploads`, якщо Railway Volume підключено.

## AI-перевірка письмових відповідей 5–11

Task 4C додає окремий безпечний grading-профіль для письмових завдань.
У Railway Variables рекомендовано додати:

```text
OPENAI_GRADING_MODEL=gpt-4o-mini
OPENAI_WRITTEN_GRADING_MAX_OUTPUT_TOKENS=2600
OPENAI_WRITTEN_GRADING_ENABLED=1
```

- `OPENAI_GRADING_MODEL` задає модель лише для перевірки письмових відповідей;
- `OPENAI_WRITTEN_GRADING_MAX_OUTPUT_TOKENS` обмежує розмір структурованої оцінки;
- `OPENAI_WRITTEN_GRADING_ENABLED=0` миттєво вимикає зовнішню перевірку та
  залишає надійний серверний fallback.

За одну фінальну спробу виконується не більше одного batch-запиту для
неоднозначних відповідей 5–11. Якщо сервер уже впевнено підтвердив повний бал,
AI-виклик для цього завдання пропускається. Завдання 12 у Task 4C не
відправляється в цей grading-процес: фото або текст для нього буде окремим
етапом Task 4D.

AI не записує оцінку напряму в базу. Після відповіді моделі сервер перевіряє
ідентифікатори, максимальні бали, критерії, рівень упевненості та незмінність
quiz snapshot. XP, прогрес і відкриття наступного уроку зберігаються лише
авторитетною транзакцією Mentory.

Якщо модель недоступна, повернула неправильний JSON або grading вимкнений,
учень усе одно завершує тест через детерміновану серверну перевірку.
