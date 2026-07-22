# Install Task 5.1 · Personal Focus & Compact Route

This patch is installed on top of `Mentory_Task5_V1_BETA_READY`.

## PowerShell

```powershell
Set-Location 'C:\Users\Derossi\Documents\Mentory\Mentory_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\Mentory_Task5_1_PERSONAL_FOCUS_COMPACT_ROUTE_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Task 5.1 archive was not found in Downloads."
}

$temp = Join-Path $env:TEMP "Mentory_Task5_1"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\Mentory_Public" "." /E `
    /XD .git .venv instance __pycache__ .pytest_cache `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed with code $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
python -m compileall -q .

git add .
git commit -m "Task 5.1: personalize focus and compact lesson route"
git push origin codex/production-hardening
```

After Railway becomes **Active**, open the dashboard and verify:

1. Only three nearby topics are visible.
2. “Інші уроки” opens the complete library.
3. After a quiz, “Персональний фокус” names the skill where the most points were lost.
4. “Відкрити останній розбір” opens the correct result page.
