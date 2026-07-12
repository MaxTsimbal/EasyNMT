# OpenAI setup for EasyNMT v0.9.8

EasyNMT уже використовує OpenAI Responses API через `client.responses.create(...)`.

## Railway Variables

```text
OPENAI_API_KEY=твій_секретний_ключ
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_OUTPUT_TOKENS=500
OPENAI_DAILY_LIMIT=40
OPENAI_MAX_QUESTION_CHARS=1500
```

Після додавання змінних зроби Redeploy. Ключ не вставляй у GitHub або JavaScript.

Без ключа сайт працює в демо-режимі. Якщо API тимчасово недоступне, користувач також отримує безпечну демо-відповідь.
