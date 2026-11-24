@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe not found.
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m upstox_project.database.database_backup
exit /b %ERRORLEVEL%