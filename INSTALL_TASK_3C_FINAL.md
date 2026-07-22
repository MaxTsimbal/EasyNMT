# Task 3C Final Candidate — встановлення

Цей пакет завершує погоджений обсяг Task 3C для production-тестів:

- людське серверне оцінювання коротких і розгорнутих відповідей;
- конкретні, зрозумілі завдання замість назв навичок;
- контекстний Easy у production-уроках;
- обмежений Easy у тестах, який пояснює умову, але не видає відповідь;
- збереження чинної логіки 12 питань, 24 балів, прохідного результату 18/24,
  XP та відкриття наступної теми.

## Важливо перед встановленням

Не видаляй поточну папку `Mentory_Public`.

Пакет треба накласти поверх чинного проєкту. Так збережуться:

- `.git`;
- `.env`;
- `.venv`;
- локальна `instance/users.db`;
- Railway Volume та production-дані.

Не встановлюй окремий архів `Task 3C.1.1 Human Answer Grading Hotfix`: його
функціональність уже включена в цей фінальний пакет і розширена Contextual Easy.

## Безпечне встановлення у Windows PowerShell

Перебуваючи в папці чинного проєкту:

```powershell
Set-Location 'C:\Users\Derossi\Documents\Mentory\Mentory_Public'

$zip = Get-ChildItem "$env:USERPROFILE\Downloads\Mentory_Task3C_FINAL_Human_Grading_Contextual_Easy_READY*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $zip) {
    throw "Фінальний архів Task 3C не знайдено у Downloads."
}

$temp = Join-Path $env:TEMP "Mentory_Task3C_FINAL_Install"
Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip.FullName -DestinationPath $temp -Force

robocopy "$temp\Mentory_Public" "." /E `
    /XD .git .venv instance __pycache__ `
    /XF .env *.pyc *.db *.sqlite *.sqlite3

if ($LASTEXITCODE -ge 8) {
    throw "Помилка копіювання Robocopy. Код: $LASTEXITCODE"
}

Remove-Item $temp -Recurse -Force
Write-Host "Task 3C Final Candidate встановлено."
```

## Перевірка після копіювання

```powershell
Write-Host ".git:" (Test-Path .\.git)
Write-Host ".env:" (Test-Path .\.env)
Write-Host ".venv:" (Test-Path .\.venv\Scripts\python.exe)
Write-Host "database:" (Test-Path .\instance\users.db)

.\.venv\Scripts\python.exe -m compileall -q .
.\.venv\Scripts\python.exe -m unittest discover -s tests -q

git --no-pager diff --check
git status --short
```

Усі чотири `Test-Path` мають повернути `True`. Пакет не потребує окремого
bootstrap або ручної міграції бази. Не додавай `.env`, `.db` чи резервні копії
бази в Git.

## Локальна smoke-перевірка

```powershell
.\.venv\Scripts\python.exe app.py
```

Відкрий `http://127.0.0.1:5000`, потім перевір:

1. production-урок відкривається за `/curriculum/units/<unit_id>/lesson`;
2. справа є компактний Easy у режимі допомоги з уроком;
3. production-тест відкривається за `/curriculum/units/<unit_id>/quiz`;
4. кнопка `Пояснити з Easy` прив’язує помічника до конкретного питання;
5. Easy пояснює простіше, але відмовляється назвати або підтвердити відповідь;
6. короткі правильні відповіді своїми словами отримують бали;
7. правильний фінальний результат у задачах 9–11 не оцінюється в нуль лише через
   відсутність повного AI-подібного пояснення.

## Публікація

Після локальної перевірки:

```powershell
git add .
git commit -m "Complete Task 3C human grading and contextual Easy"
git push origin codex/production-hardening
```

Railway має бути підключений до гілки `codex/production-hardening`, а Volume має
бути змонтований у `/app/instance`.

## OpenAI та fallback

З `OPENAI_API_KEY` Easy дає повніші контекстні пояснення через центральний AI
orchestrator. Без ключа уроки й тести не падають: сервер повертає безпечні
локальні підказки. Запити, які прямо просять відповідь під час тесту,
блокуються до виклику OpenAI й не витрачають AI-квоту.
