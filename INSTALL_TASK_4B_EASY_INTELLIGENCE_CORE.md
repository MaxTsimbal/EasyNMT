# Встановлення Task 4B — Easy Intelligence Core

Патч встановлюється поверх поточного `EasyNMT_Public` із Task 4A.
Базу даних, Railway Volume та прогрес учнів видаляти не потрібно.

## 1. Накласти архів

Розпакуй архів. Скопіюй вміст папки `EasyNMT_Public` у:

```text
C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public
```

Підтвердь заміну файлів.

## 2. Перевірити

У VS Code Terminal:

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'
python -m compileall -q .
python -m unittest discover -v
python -m pip check
```

Очікуваний результат тестів:

```text
Ran 168 tests
OK
```

## 3. Опублікувати

```powershell
git add .
git commit -m "Task 4B: Easy intelligence core"
git push origin codex/production-hardening
```

Railway автоматично запустить новий deploy.

## 4. Налаштування моделей

Оновлення безпечне зі старими Railway Variables. Якщо нові змінні не додані,
усі профілі використовують значення `OPENAI_MODEL`.

Для окремої маршрутизації додай у Railway Variables:

```text
OPENAI_TUTOR_FAST_MODEL=gpt-4o-mini
OPENAI_TUTOR_MODEL=gpt-4o-mini
OPENAI_TUTOR_REASONING_MODEL=gpt-4o-mini
OPENAI_VISION_MODEL=gpt-4o-mini
```

Спочатку залиш однакові значення. Після перевірки бюджету можна вказати
сильнішу reasoning-сумісну модель лише в
`OPENAI_TUTOR_REASONING_MODEL`.

## 5. Швидка публічна перевірка

Після статусу Railway `Active`:

1. Напиши Easy: `Коротко: що таке корінь рівняння?`.
2. Напиши: `Розв’яжи покроково систему рівнянь і перевір кожен крок`.
3. Напиши: `Я все одно не зрозумів, поясни з нуля інакше`.
4. Створи нову розмову з того самого предмета і перевір, що Easy зберіг
   простіший покроковий стиль.
5. Відкрий `/api/ai/status` після входу та перевір наявність чотирьох полів
   моделей.

Таблиця `ai_learner_memory` створиться автоматично під час запуску застосунку.
