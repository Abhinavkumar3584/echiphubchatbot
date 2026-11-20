@echo off
setlocal EnableExtensions
rem =====================================================================
rem  ingest.bat  -  builds the knowledge base from echiphubdata on THIS
rem                 laptop, then replaces it on the AWS server.
rem  Stop the chatbot on the laptop first (the database allows one program).
rem  On the server the bot is down for about 30-60 seconds. If the new
rem  knowledge base does not start, the previous one is restored by itself.
rem =====================================================================
set "KEY=%USERPROFILE%\.ssh\wp.pem"
set "SERVER=ubuntu@3.111.220.155"
cd /d "%~dp0.."
if not exist "%KEY%" goto nokey
if not exist api.py goto wrongdir

echo.
echo === 1/3  Building the knowledge base on the laptop
call .venv\Scripts\activate.bat || goto fail
python ingest.py --rebuild || goto fail

echo.
echo === 2/3  Uploading it to the server
tar -czf "%TEMP%\chatbot-data.tar.gz" --exclude .lock data/qdrant data/index_meta.json || goto fail
scp -i "%KEY%" -o ConnectTimeout=20 "%TEMP%\chatbot-data.tar.gz" %SERVER%:/tmp/chatbot-data.tar.gz || goto noconn

echo.
echo === 3/3  Switching the server to the new knowledge base
for /f "delims=:" %%a in ('findstr /n /b "#__BASH__" "%~f0"') do set "LINE=%%a"
more +%LINE% "%~f0" | ssh -i "%KEY%" -o ConnectTimeout=20 %SERVER% "tr -d '\r' | bash -s" || goto fail

echo.
echo Knowledge base updated on the server.
pause
exit /b 0

:nokey
echo SSH key not found: %KEY%
echo Copy wordpress-test.pem to that path, or change KEY= at the top of this file.
pause
exit /b 1
:wrongdir
echo Put this file in the bat_deploy folder inside the chatbot folder.
pause
exit /b 1
:noconn
echo Cannot reach the server over SSH. If your internet IP changed, ask for the SSH rule to be updated.
pause
exit /b 1
:fail
echo.
echo FAILED - read the message above.
pause
exit /b 1

#__BASH__
main() {
set -e
cd ~/chatbot
echo "== stopping the chatbot"
sudo systemctl stop chatbot
rm -rf data/qdrant-prev
if [ -d data/qdrant ]; then mv data/qdrant data/qdrant-prev; fi
if [ -f data/index_meta.json ]; then cp data/index_meta.json data/index_meta.prev.json; fi
tar -xzf /tmp/chatbot-data.tar.gz -C ~/chatbot
rm -f /tmp/chatbot-data.tar.gz
echo "== starting the chatbot"
sudo systemctl start chatbot
for i in $(seq 1 40); do
  sleep 3
  if curl -s http://127.0.0.1:8002/health | grep -q '"ok":true'; then
    echo "OK: $(curl -s http://127.0.0.1:8002/health)"
    return 0
  fi
done
echo "The new knowledge base did not start - restoring the previous one"
sudo systemctl stop chatbot
rm -rf data/qdrant
mv data/qdrant-prev data/qdrant
if [ -f data/index_meta.prev.json ]; then mv data/index_meta.prev.json data/index_meta.json; fi
sudo systemctl start chatbot
return 1
}
main
