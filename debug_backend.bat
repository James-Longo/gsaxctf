@echo off
echo Starting Backend in Debug Mode...
cd /d %~dp0
call .\.venv\Scripts\activate
echo Environment activated.
echo Running Uvicorn...
python -m uvicorn backend.main:app --port 8000 --log-level debug
if %errorlevel% neq 0 (
    echo.
    echo SERVER CRASHED! See error details above.
    pause
)
pause
