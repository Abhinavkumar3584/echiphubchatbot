@echo off
rem Scrapes all eChipHub websites using Playwright into the echiphub folder.
cd /d "%~dp0"
call .venv\Scripts\activate || (echo Run setup.bat first. & pause & exit /b 1)
python scraper_master.py %*
echo.
echo Next: 2-load.bat to load the scraped data into the vector database.
pause
