@echo off
cd /d "%~dp0"

echo Starting Event Analytics Dashboard...
echo Open http://localhost:3005 in your browser.
echo Press Ctrl+C to stop the server.
echo.

python run.py

pause
