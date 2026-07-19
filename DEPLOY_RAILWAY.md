# EasyNMT: публікація на Railway

## Файли вже підготовлені
- `Procfile` і `railway.json` запускають сайт через Gunicorn.
- `/health` перевіряє, що вебпроцес відповідає; `/ready` окремо перевіряє
  доступність та ініціалізацію SQLite.
- SQLite автоматично використовує Railway Volume.
- Локально база лишається в `instance/users.db`.

## Налаштування Railway
1. Завантаж проєкт у приватний GitHub-репозиторій.
2. У Railway створи **New Project → Deploy from GitHub repo**.
3. Додай Volume до сервісу з mount path: `/data`.
4. У Variables додай:
   - `SECRET_KEY` = випадковий довгий секретний рядок
   - `FLASK_DEBUG` = `0`
   - `SESSION_COOKIE_SECURE` = `1`
   - `OPENAI_MODEL` = `gpt-4o-mini`
   - `OPENAI_DAILY_LIMIT` = `40`
   - `OPENAI_API_KEY` = ключ провайдера (необов’язковий для офлайн-режиму)
5. В Settings → Networking натисни **Generate Domain**.

Railway автоматично передає `RAILWAY_VOLUME_MOUNT_PATH`, тому EasyNMT збереже базу на підключеному Volume.
