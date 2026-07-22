# Mentory v1.0 Beta: публікація на Railway

## Runtime

- `railway.json` і `Procfile` запускають один Gunicorn worker із 4 threads.
- `/health` є легкою liveness-перевіркою.
- `/ready` перевіряє SQLite, Volume, backup, OpenAI config, OAuth config і runtime.
- SQLite та backups використовують `RAILWAY_VOLUME_MOUNT_PATH`.

## Railway setup

1. Deploy GitHub branch `codex/production-hardening`.
2. Додай Volume до сервісу, наприклад mount path `/data`.
3. Додай Variables:

```text
SECRET_KEY=<random 32+ chars>
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=1
OPENAI_API_KEY=<real key>
WEB_CONCURRENCY=1
EASYNMT_AUTO_BACKUP=1
EASYNMT_BACKUP_INTERVAL_HOURS=24
EASYNMT_BACKUP_MAX_AGE_HOURS=30
EASYNMT_BACKUP_RETENTION=7
EASYNMT_BETA_REQUIRE_PERSISTENT_VOLUME=1
EASYNMT_BETA_REQUIRE_OPENAI=1
EASYNMT_BETA_REQUIRE_BACKUP=1
EASYNMT_BETA_REQUIRE_GOOGLE_OAUTH=0
EASYNMT_ALLOW_DETERMINISTIC_LESSON_FALLBACK=0
```

4. Додай OpenAI model variables із `.env.example`.
5. Для Google Login додай `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` і callback.
6. Generate Domain.

## Після deployment

- `/health` має повернути 200 і release `1.0.0-beta.2`.
- `/ready` має повернути 200 і `status: ready`.
- Пройди `BETA_MANUAL_TEST_CHECKLIST.md`.
- Перед важливою зміною створи backup:

```text
python -m flask --app app beta backup --reason before-release
```

Не запускай кілька Railway replicas з однією SQLite базою. Для горизонтального
масштабування потрібен окремий перехід на PostgreSQL.
