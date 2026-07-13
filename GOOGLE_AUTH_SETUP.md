# Google Sign-In для EasyNMT v0.9.9.5

## Google Cloud

OAuth Client має бути типу **Web application**.

Authorized JavaScript origin:

```text
https://easynmt.up.railway.app
```

Authorized redirect URI:

```text
https://easynmt.up.railway.app/auth/google/callback
```

Адреса повинна збігатися символ у символ.

## Railway Variables

Потрібні лише:

```text
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SECRET_KEY=довгий-випадковий-рядок
SESSION_COOKIE_SECURE=1
```

`GOOGLE_REDIRECT_URI` більше не потрібна: Flask автоматично створює HTTPS callback.

## Перевірка

Безпечний статус:

```text
https://easynmt.up.railway.app/auth/google/status
```

Очікувано:

```json
{
  "client_id_present": true,
  "client_secret_present": true,
  "google_client_ready": true,
  "implementation": "oauth2_requests"
}
```

Секрет, який потрапляв на скріншот, потрібно замінити в Google Cloud та Railway.
