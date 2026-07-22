# OpenAI Integration Map

## Єдина точка входу

Усі виклики моделі проходять через:

```python
from easynmt_ai.service import OpenAIResponsesProvider
```

Маршрути Flask працюють через `AIOrchestrator`, а не через SDK напряму.

## Потік запиту

```text
UI
→ /api/tutor-chat/stream
→ LearningContext
→ AIRequest
→ AIOrchestrator
→ OpenAIResponsesProvider
→ Responses API
→ SSE deltas
→ UI
```

## Контекст Mentory

До моделі передаються лише потрібні навчальні дані:
- предмет;
- ціль;
- час до НМТ;
- прогрес;
- XP і серія;
- поточний урок;
- слабка тема;
- останні повідомлення поточної розмови;
- фото, які користувач прикріпив до конкретного запиту.

## Environment variables

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_MAX_OUTPUT_TOKENS=900
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=1
OPENAI_STORE_RESPONSES=0
OPENAI_DAILY_LIMIT=40
OPENAI_MAX_QUESTION_CHARS=1500
AI_MAX_ATTACHMENTS=3
AI_DAILY_UPLOAD_LIMIT=20
AI_MAX_ATTACHMENT_BYTES=5242880
```

## Наступний крок

Під час старту `Mentory v1.0 Beta` не потрібно знову перебудовувати чат. Потрібно тестувати промпти, моделі, ціну, якість оцінювання та інтеграцію AI в уроки й тести.
