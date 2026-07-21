# Install Task 4A — Learning-Ready Lesson Standard

This package is an overlay for the current `EasyNMT_Public` project after Task 3D.4.

## PowerShell installation

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\EasyNMT_Task4A_LEARNING_READY_LESSONS_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Task 4A archive was not found in Downloads."
}

$temp = Join-Path $env:TEMP "EasyNMT_Task4A_LearningReadyLessons"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\EasyNMT_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed. Code: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 4A installed."
```

## Publish

```powershell
Set-Location 'C:\Users\Derossi\Documents\EasyNMT\EasyNMT_Public'
git add .
git commit -m "Task 4A: add learning-ready guided practice"
git push origin codex/production-hardening
```

Railway should deploy the pushed commit automatically.

## Production note

The lesson prompt and schema identities were bumped. Newly opened units receive the new learning-ready lesson structure. Existing immutable lesson rows remain untouched and safe for audit/history.
