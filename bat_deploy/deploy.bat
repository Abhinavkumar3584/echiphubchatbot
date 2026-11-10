@echo off
rem Sends the chatbot to the AWS server.  First time: bat_deploy\deploy.bat -Full   Later: bat_deploy\deploy.bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1" %*
