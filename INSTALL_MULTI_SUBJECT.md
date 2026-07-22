# Mentory Task 3B.3: встановлення мультипредметного оновлення

Цей архів переводить усі активні предмети Mentory на спільну Production Lesson Platform:

- Математика — 39 тем
- Українська мова — 12 тем
- Історія України — 12 тем
- Англійська мова — 12 тем

## 1. Зробіть резервну копію

Перед заміною файлів скопіюйте всю поточну папку `Mentory_Public` у безпечне місце.

Не видаляйте власні файли:

- `.env`
- `instance/users.db`
- завантаження користувачів

Вони навмисно не входять до цього архіву.

## 2. Розпакуйте архів

Розпакуйте вміст архіву поверх поточної папки:

```text
C:\Users\Derossi\Documents\Mentory\Mentory_Public
```

Погодьтеся на заміну програмних файлів.

## 3. Створіть production curricula для всіх предметів

Найпростіший варіант: двічі натисніть файл:

```text
bootstrap_all_subjects.bat
```

Або виконайте у PowerShell:

```powershell
Set-Location 'C:\Users\Derossi\Documents\Mentory\Mentory_Public'
.\.venv\Scripts\python.exe -m flask --app app curriculum status
.\.venv\Scripts\python.exe -m flask --app app curriculum bootstrap-development --all-subjects
.\.venv\Scripts\python.exe -m flask --app app curriculum status
```

Команда безпечна для повторного запуску: наявні curricula повторно використовуються, відсутні додаються, прогрес не стирається.

## 4. Запустіть сайт

```powershell
.\.venv\Scripts\python.exe app.py
```

Відкрийте:

```text
http://127.0.0.1:5000
```

## 5. Перевірка

Для кожного предмета:

1. Перемкніть предмет у звичайному інтерфейсі.
2. Відкрийте Dashboard.
3. Натисніть продовження або першу картку уроку.
4. Адреса повинна мати вигляд:

```text
/curriculum/units/<unit_id>/lesson
```

Активні предмети з опублікованим curriculum більше не повинні відкривати `/lesson/<id>`.

Після завершення уроку стан переходить у `assessment_required`. Це очікувано: Production Quiz Engine буде реалізовано окремо в Task 3C.

## Railway

Автоматичний bootstrap у production вимкнений. Для безпечного явного запуску потрібні одночасно:

- CLI-прапорець `--allow-production`
- змінна `EASYNMT_ALLOW_PRODUCTION_CURRICULUM_BOOTSTRAP=1`

Не запускайте production bootstrap без резервної копії Railway volume/database.
