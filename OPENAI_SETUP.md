# Підключення OpenAI до EasyNMT

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

## Контроль витрат

- денний ліміт задає `OPENAI_DAILY_LIMIT`;
- ліміт резервується атомарно перед зовнішнім викликом, тому паралельні запити
  не можуть перевищити його;
- довжину відповіді обмежує `OPENAI_MAX_OUTPUT_TOKENS`;
- максимум фото в одному запиті задає `AI_MAX_ATTACHMENTS`, розмір — `AI_MAX_ATTACHMENT_BYTES`, денний ліміт — `AI_DAILY_UPLOAD_LIMIT`;
- усі виклики проходять через `easynmt_ai/service.py`.

## Фото

AI Викладач приймає PNG, JPG, JPEG і WEBP до 5 МБ. Фото зберігаються у `RAILWAY_VOLUME_MOUNT_PATH/ai_uploads`, якщо Railway Volume підключено.
