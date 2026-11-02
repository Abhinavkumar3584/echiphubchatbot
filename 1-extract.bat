@echo off
rem Reads the eChipHub websites and writes the clean pages to output\pages (asks your Keycloak login).
rem Add --fresh to start over. Already extracted? "1-extract.bat build" only cleans again (no internet).
cd /d "%~dp0"
call .venv\Scripts\activate || (echo Run setup.bat first. & pause & exit /b 1)
if "%~1"=="" (python extractor\extract.py run) else (python extractor\extract.py %*)
echo.
echo Next: 2-load.bat.   Remember to delete output\session.json when you are finished extracting.
pause
