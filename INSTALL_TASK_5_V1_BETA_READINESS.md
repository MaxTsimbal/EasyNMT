# Встановлення Task 5 · EasyNMT v1.0 Beta

Це cumulative package. Він уже містить Task 3D.4, 4A, 4B, 4C, 4D і Task 5,
тому його можна накласти поверх поточного `EasyNMT_Public` без послідовного
копіювання п’яти попередніх архівів. `.env`, `.git`, база, Volume і backups не
перезаписуються.

## 1. Встановлення

У VS Code → Terminal встав одним блоком:

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\EasyNMT_Task5_V1_BETA_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) { throw "Архів Task 5 не знайдено у Downloads." }

$temp = Join-Path $env:TEMP "EasyNMT_Task5_V1_Beta"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\EasyNMT_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache backups `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Помилка копіювання Robocopy. Код: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 5 встановлено."
```

## 2. Локальна перевірка

```powershell
python -m pip install -r requirements.txt
python -m compileall -q .
python -m unittest discover -v
python -m pip check
python -m flask --app app beta check
python -m flask --app app beta smoke
```

## 3. Railway Variables

Обов’язково:

```text
SECRET_KEY=<випадковий рядок 32+ символи>
FLASK_DEBUG=0
SESSION_COOKIE_SECURE=1
OPENAI_API_KEY=<реальний ключ>
WEB_CONCURRENCY=1
EASYNMT_AUTO_BACKUP=1
EASYNMT_BACKUP_RETENTION=7
EASYNMT_BETA_REQUIRE_PERSISTENT_VOLUME=1
EASYNMT_BETA_REQUIRE_OPENAI=1
EASYNMT_BETA_REQUIRE_BACKUP=1
EASYNMT_ALLOW_DETERMINISTIC_LESSON_FALLBACK=0
```

Railway Volume має бути підключений до сервісу. Google OAuth можна залишити
необов’язковим через `EASYNMT_BETA_REQUIRE_GOOGLE_OAUTH=0`.

## 4. Публікація

```powershell
git add .
git commit -m "Task 5: prepare EasyNMT v1.0 Beta"
git push origin codex/production-hardening
```

Після зеленого deployment відкрий `/health`, потім `/ready`, а далі проходь
`BETA_MANUAL_TEST_CHECKLIST.md`.
