@echo off
echo ==============================================
echo Updating Google Photos Albums Metadata...
echo ==============================================
cd /d %~dp0

.\.venv\Scripts\python backend\update_albums.py

echo.
pause
