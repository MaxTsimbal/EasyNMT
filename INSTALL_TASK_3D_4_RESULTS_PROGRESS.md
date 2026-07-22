# Install Task 3D.4 — Results, XP & Progress Sync

This package is an overlay for the current `Mentory_Public` project that already contains Task 3D.3.

## PowerShell installation

```powershell
Set-Location 'C:\Users\Derossi\Documents\Mentory\Mentory_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\Mentory_Task3D_4_RESULTS_PROGRESS_SYNC_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Task 3D.4 archive was not found in Downloads."
}

$temp = Join-Path $env:TEMP "Mentory_Task3D_4_ResultsProgress"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\Mentory_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed. Code: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 3D.4 installed."
```

## Publish

```powershell
Set-Location 'C:\Users\Derossi\Documents\Mentory\Mentory_Public'
git add .
git commit -m "Task 3D.4: sync quiz results XP and progress"
git push origin codex/production-hardening
```

Railway should deploy the pushed commit automatically.
