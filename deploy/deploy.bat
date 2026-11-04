@echo off
rem Sends the chatbot to the AWS server.  First time: deploy\deploy.bat -Full   Later: deploy\deploy.bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" %*
