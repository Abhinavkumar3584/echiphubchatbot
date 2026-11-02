@echo off
rem Tests the bot with golden.csv.  "test.bat --answers" also checks the answers (uses Groq).
cd /d "%~dp0"
call .venv\Scripts\activate || (echo Run setup.bat first. & pause & exit /b 1)
python evaluate.py %*
pause
