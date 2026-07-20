@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

echo.
echo [1/3] Current curriculum status
"%PYTHON%" -m flask --app app curriculum status
if errorlevel 1 goto :error

echo.
echo [2/3] Provisioning all active subjects
"%PYTHON%" -m flask --app app curriculum bootstrap-development --all-subjects
if errorlevel 1 goto :error

echo.
echo [3/3] Final curriculum status
"%PYTHON%" -m flask --app app curriculum status
if errorlevel 1 goto :error

echo.
echo All active subjects are ready. Start the site with:
echo "%PYTHON%" app.py
pause
exit /b 0

:error
echo.
echo Curriculum bootstrap failed. Read the error above before retrying.
pause
exit /b 1
