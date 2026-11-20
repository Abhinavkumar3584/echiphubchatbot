@echo off
setlocal EnableExtensions
rem =====================================================================
rem  extract.bat  -  scrapes the eChipHub websites on THIS laptop
rem                  into the echiphubdata folder (scraper_master.py).
rem  Runs on the laptop on purpose: no browser is installed on the server.
rem  Next: ingest.bat
rem =====================================================================
cd /d "%~dp0.."
if not exist scraper_master.py (
  echo Put this file in the bat_deploy folder inside the chatbot folder.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat || (
  echo Run setup.bat first.
  pause
  exit /b 1
)
python scraper_master.py %*
if errorlevel 1 (
  echo.
  echo FAILED - read the message above.
  pause
  exit /b 1
)
echo.
echo Websites scraped into echiphubdata.  Next: ingest.bat
pause
