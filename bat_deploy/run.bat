@echo off
setlocal EnableExtensions
rem =====================================================================
rem  run.bat  -  (re)starts the chatbot on the AWS server and checks it.
rem  The chatbot then runs permanently (it also restarts after a crash or
rem  a server reboot) at https://chat-test.echiphub.in  -  same port 8002.
rem  You can close this window afterwards; the bot keeps running.
rem =====================================================================
set "KEY=%USERPROFILE%\.ssh\wp.pem"
set "SERVER=ubuntu@3.111.220.155"
cd /d "%~dp0.."
if not exist "%KEY%" goto nokey
if not exist api.py goto wrongdir

echo.
echo === Starting the chatbot on the server
for /f "delims=:" %%a in ('findstr /n /b "#__BASH__" "%~f0"') do set "LINE=%%a"
more +%LINE% "%~f0" | ssh -i "%KEY%" -o ConnectTimeout=20 %SERVER% "tr -d '\r' | bash -s" || goto fail

echo.
echo The chatbot is live at https://chat-test.echiphub.in
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
echo "== (re)starting the chatbot"
sudo systemctl enable chatbot > /dev/null 2>&1 || true
sudo systemctl restart chatbot
for i in $(seq 1 40); do
  sleep 3
  if curl -s http://127.0.0.1:8002/health | grep -q '"ok":true'; then break; fi
done
echo "chatbot service : $(systemctl is-active chatbot)"
echo "public health   : $(curl -s -m 20 https://chat-test.echiphub.in/health)"

echo "== test question (answered by Amazon Bedrock)"
START=$(date +%s)
ANS=$(curl -s -m 120 -X POST http://127.0.0.1:8002/api/chat -H 'Content-Type: application/json' -d '{"message":"What is eChipHub?"}')
echo "answered in $(( $(date +%s) - START )) seconds:"
echo "$ANS" | head -c 400
echo
echo "== memory"
free -h | head -2
if ! echo "$ANS" | grep -q '"answer"'; then
  echo "No answer - last log lines:"
  sudo journalctl -u chatbot -n 20 --no-pager
  return 1
fi
}
main
