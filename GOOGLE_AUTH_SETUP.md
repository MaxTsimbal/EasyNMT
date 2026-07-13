# Google Sign-In для EasyNMT

## 1. Створи OAuth-клієнт у Google Cloud

1. Відкрий Google Cloud Console.
2. Створи або вибери проєкт EasyNMT.
3. Налаштуй OAuth consent screen.
4. Створи OAuth Client ID типу **Web application**.
5. Додай дозволені redirect URI без зайвого слеша в кінці:

Локально:
```
http://127.0.0.1:5000/auth/google/callback
```

Для Railway:
```
https://ТВІЙ-ДОМЕН/auth/google/callback
```

## 2. Додай Railway Variables

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://ТВІЙ-ДОМЕН/auth/google/callback
SESSION_COOKIE_SECURE=1
SECRET_KEY=довгий-випадковий-секрет
```

Client Secret не додавай у GitHub, `.env.example` або JavaScript.

## 3. Перезапусти deploy

Після додавання Variables Railway виконає новий deploy. Потім відкрий сторінку входу та натисни «Увійти через Google».

## Часті помилки

- `redirect_uri_mismatch`: адреса callback у Google Cloud не збігається символ у символ із `GOOGLE_REDIRECT_URI`.
- Google-вхід не налаштований: у Railway немає Client ID або Client Secret.
- Повернення на `http://`: перевір `GOOGLE_REDIRECT_URI` і `SESSION_COOKIE_SECURE=1`.
