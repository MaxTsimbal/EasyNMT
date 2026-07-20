# Installing Task 3C.1 Safely

Do not delete the existing project directory. The archive intentionally does
not contain `.git`, `.env`, `.venv`, or `instance/users.db`.

## Windows installation

1. Make a copy of the current project directory.
2. Extract this archive into a separate temporary folder.
3. From the current project directory, copy only source-controlled files:

```powershell
robocopy "C:\path\to\extracted\EasyNMT_Public" "." /E /XD .git .venv instance __pycache__ /XF .env *.pyc
```

4. Verify that private/runtime files still exist:

```powershell
Test-Path .\.git
Test-Path .\.env
Test-Path .\.venv\Scripts\python.exe
Test-Path .\instance\users.db
```

5. Run verification:

```powershell
.\.venv\Scripts\python.exe -m compileall -q .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

6. Review and deploy:

```powershell
git status
git add .
git commit -m "Add Task 3C.1 production quiz foundation"
git push origin codex/production-hardening
```

## Railway

- Keep the persistent Volume mounted at `/app/instance`.
- The application creates the new quiz tables automatically on startup.
- Existing production curricula do not need to be bootstrapped again.
- After a successful deployment, open a completed curriculum lesson and use
  `Перейти до тесту`.
- The production quiz URL is
  `/curriculum/units/<unit_id>/quiz`.

## Scope warning

This release provides deterministic server grading. Do not present it as AI
photo grading. Those capabilities are scheduled for later Task 3C stages.
