# Task 3D Production Exam Engine — встановлення

Цей пакет накладається поверх поточного `EasyNMT_Public`. Він **не видаляє** базу, `.env`, `.git`, Railway Volume або прогрес користувачів.

## Головні зміни

- англійські тести тепер складаються з практичних вправ, а не переказу правил;
- питання 1–4: вибір форми в реальному реченні або тексті;
- питання 5–8: заперечення, питання, порядок слів, виправлення, переклад або коротка робота з текстом;
- питання 9–12: три незалежні частини по 1 балу;
- кожна завершена спроба відкриває новий детермінований варіант;
- оновлення сторінки до відправлення зберігає той самий варіант і чернетку;
- Easy v3.1 бачить тип вправи та текст, але не отримує ключ оцінювання;
- після тесту формується персональний план повторення;
- питання №12 більше не змушує повертатися до попереднього завдання.

## Встановлення у PowerShell

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\EasyNMT_Task3D_PRODUCTION_EXAM_ENGINE_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Архів Task 3D не знайдено у Downloads."
}

$temp = Join-Path $env:TEMP "EasyNMT_Task3D_ProductionExam"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\EasyNMT_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Помилка копіювання Robocopy. Код: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 3D Production Exam Engine встановлено."
```

## Перевірка

Запускай окремо:

```powershell
.\.venv\Scripts\python.exe -m compileall -q .
Write-Host "Compile code:" $LASTEXITCODE
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Write-Host "Tests code:" $LASTEXITCODE
```

Обидва коди повинні бути `0`.

## Локальний запуск

```powershell
.\.venv\Scripts\python.exe app.py
```

Відкрий `http://127.0.0.1:5000` і перевір англійський урок:

1. 1–4 питання мають чотири варіанти відповіді.
2. 5–8 містять практичні дії, наприклад заперечення, питання, порядок слів або виправлення.
3. 9–12 мають три окремі відповіді та дають по 1 балу за кожну.
4. Після оновлення сторінки чернетка підтягується до того самого варіанта.
5. Після завершення спроби кнопка «Новий варіант тесту» показує інші вправи.
6. Easy пояснює спосіб, але не видає готової відповіді.
7. На сторінці результату є план повторення слабких навичок.

## Публікація

```powershell
git add .
git commit -m "Add Task 3D production exam engine"
git push origin codex/production-hardening
```

Окрема міграція бази або повторний curriculum bootstrap не потрібні.
