# Встановлення Task 4D — Final Photo Solution

Патч встановлюється поверх поточного `EasyNMT_Public` із Task 4C.
Базу даних, Railway Volume, акаунти, результати й прогрес видаляти не потрібно.

## 1. Накласти архів

Розпакуй архів і скопіюй вміст папки `EasyNMT_Public` у:

```text
C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public
```

Підтвердь заміну файлів.

## 2. Перевірити локально

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'
python -m compileall -q .
python -m pytest -q
python -m pip check
```

Очікуваний результат:

```text
191 passed
```

## 3. Опублікувати

```powershell
git add .
git commit -m "Task 4D: final photo solution grading"
git push origin codex/production-hardening
```

Railway автоматично почне новий deploy.

## 4. Railway Variables

Перевір або додай:

```text
OPENAI_FINAL_SOLUTION_ENABLED=1
OPENAI_FINAL_SOLUTION_MODEL=gpt-4o-mini
OPENAI_FINAL_SOLUTION_MAX_OUTPUT_TOKENS=1800
QUIZ_SOLUTION_PHOTO_MAX_BYTES=6291456
QUIZ_SOLUTION_PHOTO_MAX_DIMENSION=2400
```

`OPENAI_FINAL_SOLUTION_MODEL` може бути тією самою vision-моделлю, що й
`OPENAI_VISION_MODEL`. Якщо окрему змінну не вказати, Easy успадкує
`OPENAI_VISION_MODEL`.

## 5. Публічна smoke-перевірка

1. Заверши урок і відкрий новий тест.
2. Переконайся, що фото можна додати лише в запитанні №12.
3. Завантаж чітке фото аркуша у PNG, JPG або WEBP.
4. Не вводь текст у №12: фото саме має зарахувати питання як заповнене.
5. Заверши тест і перевір позначку `Easy Vision`, три критерії та часткові бали.
6. Створи нову спробу та подай №12 лише текстом: тест повинен працювати без фото.
7. Створи ще одну спробу з фото й текстом: результат має показати `Фото + текст`.
8. Онови сторінку результату: бал, XP і прогрес не повинні змінитися.

## 6. Перевірка нечіткого фото та fallback

- Нечитабельне фото без тексту не повинно отримати прихований нуль. Easy
  повертає учня до №12 з проханням перефотографувати або додати текст.
- Якщо vision-перевірка тимчасово недоступна, фото без тексту не завершує
  спробу. Фото + текст оцінюється за текстовим серверним fallback.
- Для аварійного відключення встанови `OPENAI_FINAL_SOLUTION_ENABLED=0`.
  Текстовий варіант №12 продовжить працювати.
