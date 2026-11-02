@echo off
rem Starts the chatbot at http://localhost:8000  (close this window to stop it)
cd /d "%~dp0"
call .venv\Scripts\activate || (echo Run setup.bat first. & pause & exit /b 1)
start "" http://localhost:8000
python -m uvicorn api:app --port 8000
pause
