# Task 3D.3 — Quiz 409 Stability Recovery

Цей архів накладається поверх поточної версії EasyNMT у гілці `codex/production-hardening`.

## Що виправлено

- тест більше не повинен одразу відкривати сторінку `409`;
- старий або змінений шаблон тесту безпечно оновлюється в базі;
- активна незавершена спроба повторно відкривається після оновлення сторінки;
- пошкоджена незавершена сесія автоматично замінюється;
- повторне надсилання завершеної спроби залишається ідемпотентним;
- старі формати часу більше не ламають перевірку строку дії сесії.

Окремо видаляти SQLite-базу, Railway Volume, користувачів або прогрес не потрібно.

## Встановлення через PowerShell

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\EasyNMT_Task3D_3_QUIZ_409_STABILITY_FIX_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Архів Task 3D.3 не знайдено у Downloads."
}

$temp = Join-Path $env:TEMP "EasyNMT_Task3D_3_Quiz409"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\EasyNMT_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Помилка копіювання Robocopy. Код: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 3D.3 встановлено."
```

## Перевірка

```powershell
.\.venv\Scripts\python.exe -m compileall -q .
Write-Host "Compile code:" $LASTEXITCODE
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Write-Host "Tests code:" $LASTEXITCODE
```

Очікувано: `154 tests`, `OK`, обидва коди `0`.

## Публікація

```powershell
git add .
git commit -m "Fix quiz 409 session stability"
git push origin codex/production-hardening
```

Після Railway deploy відкрий завершений урок і натисни перехід до тесту. Сторінка тесту має відкритися одразу без `409`.
