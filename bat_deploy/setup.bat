@echo off
cd /d "%~dp0.."
echo === eChipHub Assistant setup (needs Python 3.12) ===
if not exist .venv (py -3.12 -m venv .venv || goto error)
call .venv\Scripts\activate || goto error
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto error
python -m pip install -r requirements-extract.txt || goto error
crawl4ai-setup || python -m playwright install chromium
if not exist .env (copy .env.example .env >nul && echo Created .env - open it and paste your Groq key.)
echo.
echo Setup finished. Next: put your Groq key in .env, then run 1-extract.bat
pause
exit /b 0
:error
echo.
echo Setup FAILED - see the message above. Is Python 3.12 installed?  (winget install Python.Python.3.12)
pause
exit /b 1
