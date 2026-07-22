# Task 3C.2 Student Clarity Final — встановлення

Це завершальний пакет виправлень для production-тестів перед переходом до етапу 4.
Він накладається поверх поточного `Mentory_Public` і вже містить попередній runtime-fix Contextual Easy v3.0.1.

## Що змінюється

- усі 12 запитань мають три окремі частини: **Що зробити**, **Завдання**, **Як відповісти**;
- абстрактні назви навичок більше не використовуються як завдання 9–12;
- додано 225 перевірених конкретних fallback-завдань: по 3 для кожної з 75 тем;
- правильна кінцева відповідь у складних завданнях оцінюється окремо від пояснення;
- короткі відповіді перевіряються за змістом, а не за дослівним повторенням еталона;
- Easy отримує видимий текст активного питання та формат відповіді, але не ключ оцінювання;
- Easy Chat v3.0.1 зберігає плавне друкування, автопрокрутку, кнопку зупинки й відсутність глобального loader;
- старі збережені quiz-снапшоти залишаються читабельними.

## Важливо

Не видаляй чинну папку проєкту. Під час копіювання мають зберегтися:

- `.git`;
- `.env`;
- `.venv`;
- папка `instance` і локальна база;
- Railway Volume з production-даними.

## Встановлення у PowerShell

```powershell
Set-Location 'C:\Users\Derossi\Documents\Mentory\Mentory_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\Mentory_Task3C_2_STUDENT_CLARITY_FINAL_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Архів Task 3C.2 Student Clarity не знайдено у Downloads."
}

$temp = Join-Path $env:TEMP "Mentory_Task3C_2_StudentClarity"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\Mentory_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Помилка копіювання Robocopy. Код: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 3C.2 Student Clarity встановлено."
```

## Перевірка

Запускай команди окремо:

```powershell
Write-Host ".git:" (Test-Path .\.git)
Write-Host ".env:" (Test-Path .\.env)
Write-Host ".venv:" (Test-Path .\.venv\Scripts\python.exe)
Write-Host "database:" (Test-Path .\instance\users.db)
```

Усі значення мають бути `True`.

```powershell
.\.venv\Scripts\python.exe -m compileall -q .
Write-Host "Compile code:" $LASTEXITCODE
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Write-Host "Tests code:" $LASTEXITCODE
```

Обидва коди мають бути `0`.

## Локальна перевірка

```powershell
.\.venv\Scripts\python.exe app.py
```

Відкрий `http://127.0.0.1:5000` і перевір:

1. у кожному питанні видно **Що зробити**, **Завдання**, **Як відповісти**;
2. питання 9–11 містять справжнє речення, задачу, текст або конкретну дію;
3. питання 12 прямо посилається на завдання №11 і просить назвати спосіб перевірки;
4. Easy пояснює активне питання простіше, не видаючи відповіді;
5. запит до Easy не запускає повноекранний loader;
6. відповідь Easy друкується плавно й прокручується автоматично;
7. правильний результат без повного пояснення отримує часткові бали, а не нуль.

Після оновлення відкрий **нову спробу тесту**. Уже розпочата спроба може зберігати старий серверний знімок запитань.

## Публікація

Після перевірки:

```powershell
git add .
git commit -m "Complete Task 3C student clarity"
git push origin codex/production-hardening
```

Окрема міграція або повторний bootstrap curriculum не потрібні.
