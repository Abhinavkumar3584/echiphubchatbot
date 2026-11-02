@echo off
rem Loads echiphub/*.json into the Qdrant database (embeddings made with BGE). Stop 3-start.bat first.
cd /d "%~dp0"
call .venv\Scripts\activate || (echo Run setup.bat first. & pause & exit /b 1)
python ingest.py %*
pause
