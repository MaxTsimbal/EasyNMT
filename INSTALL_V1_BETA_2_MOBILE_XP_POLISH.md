# Встановлення EasyNMT v1.0 Beta.2

Це накопичувальний пакет поверх поточного `EasyNMT_Public`. Він уже містить Task 5.1, персональний фокус, три найближчі теми, XP repair і мобільне полірування.

## PowerShell

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\EasyNMT_V1_BETA_2_MOBILE_XP_POLISH_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) { throw "Архів Beta.2 не знайдено у Downloads." }

$temp = Join-Path $env:TEMP "EasyNMT_V1_BETA_2"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\EasyNMT_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) { throw "Помилка копіювання Robocopy: $LASTEXITCODE" }
Remove-Item $temp -Recurse -Force

git add .
git commit -m "Release EasyNMT v1.0 Beta.2 mobile and XP polish"
git push origin codex/production-hardening
```

Після зеленого Railway `Active` відкрий кабінет або профіль. Старе завершення з `0 XP` має автоматично відновитися до підтвердженого значення.
