# Встановлення Task 4C — AI Written Answer Grading

Патч встановлюється поверх поточного `EasyNMT_Public` із Task 4B.
Базу даних, Railway Volume, акаунти та прогрес учнів видаляти не потрібно.

## 1. Накласти архів

Розпакуй архів. Скопіюй вміст папки `EasyNMT_Public` у:

```text
C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public
```

Підтвердь заміну файлів.

## 2. Перевірити локально

У VS Code Terminal:

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'
python -m compileall -q .
python -m unittest discover -s tests -q
python -m pip check
```

Очікуваний результат:

```text
Ran 180 tests
OK
```

## 3. Опублікувати

```powershell
git add .
git commit -m "Task 4C: AI written answer grading"
git push origin codex/production-hardening
```

Railway автоматично запустить новий deploy.

## 4. Railway Variables

Додай або перевір:

```text
OPENAI_GRADING_MODEL=gpt-4o-mini
OPENAI_WRITTEN_GRADING_MAX_OUTPUT_TOKENS=2600
OPENAI_WRITTEN_GRADING_ENABLED=1
```

Без цих нових змінних застосунок не падає: grading-модель успадковує
reasoning-модель, а зовнішня перевірка за замовчуванням увімкнена.
Для аварійного відключення без нового deploy встанови:

```text
OPENAI_WRITTEN_GRADING_ENABLED=0
```

Тоді тести завершуватимуться через перевірений серверний grader.

## 5. Публічна smoke-перевірка

Після статусу Railway `Active`:

1. Відкрий завершений урок і почни тест.
2. У запитанні 5–8 дай правильну відповідь своїми словами, не копіюючи ключ.
3. У запитанні 9–11 залиш частково правильне покрокове розв’язання.
4. Заповни всі 12 відповідей і заверши тест.
5. На сторінці результату перевір AI-позначку, критерії за кожен бал,
   першу помилку та наступний крок.
6. Онови сторінку результату: оцінка й XP не повинні змінитися.
7. Переконайся, що запитання 12 поки залишається текстовим фінальним
   завданням. Фото буде додано окремо у Task 4D.

## 6. Перевірка fallback

Тимчасово встанови `OPENAI_WRITTEN_GRADING_ENABLED=0`, створи нову спробу й
заверши тест. Він повинен оцінитися без сторінки помилки. Після перевірки
поверни значення `1`.
