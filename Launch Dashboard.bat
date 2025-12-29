@echo off
echo Starting Track & Field Dashboard...

:: Start Backend
start /min cmd /c "cd /d %~dp0 && .\.venv\Scripts\python -m uvicorn backend.main:app --port 8000"

:: Start Frontend
start /min cmd /c "cd /d %~dp0ui && npm run dev"

echo Waiting for services to start...
timeout /t 5 /nobreak > nul

:: Open browser
start http://localhost:5173

echo Dashboard launched! You can close this window.
pause
