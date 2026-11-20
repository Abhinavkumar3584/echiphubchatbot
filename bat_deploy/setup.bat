@echo off
setlocal EnableExtensions
rem =====================================================================
rem  setup.bat  -  prepares the laptop AND the AWS server
rem    Laptop : Python environment, packages, browser for the scraper
rem    Server : chatbot code, packages, settings (.env), service, Nginx
rem  Same server, same URL (https://chat-test.echiphub.in), same port 8002.
rem  First time, run in this order:
rem    setup.bat  ->  extract.bat  ->  ingest.bat  ->  run.bat
rem  AWS keys are NOT in this file: they are sent once to the server's .env (see README).
rem =====================================================================
set "KEY=%USERPROFILE%\.ssh\wp.pem"
set "SERVER=ubuntu@3.111.220.155"
cd /d "%~dp0.."
if not exist "%KEY%" goto nokey
if not exist api.py goto wrongdir

echo.
echo === 1/3  Laptop: Python environment and packages
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if not exist .venv\Scripts\python.exe python -m venv .venv
call .venv\Scripts\activate.bat || goto fail
python -m pip install --upgrade pip -q || goto fail
python -m pip install -q -r requirements.txt || goto fail
python -m pip install -q -r requirements-extract.txt || goto fail
python -m playwright install chromium || goto fail

echo.
echo === 2/3  Uploading the chatbot code to the server
tar -czf "%TEMP%\chatbot-code.tar.gz" api.py config.py embeddings.py llm.py guardrails.py retrieval.py vector_store.py requirements.txt static || goto fail
scp -i "%KEY%" -o ConnectTimeout=20 "%TEMP%\chatbot-code.tar.gz" %SERVER%:/tmp/chatbot-code.tar.gz || goto noconn

echo.
echo === 3/3  Setting up the server
for /f "delims=:" %%a in ('findstr /n /b "#__BASH__" "%~f0"') do set "LINE=%%a"
more +%LINE% "%~f0" | ssh -i "%KEY%" -o ConnectTimeout=20 %SERVER% "tr -d '\r' | bash -s" || goto fail

echo.
echo Setup finished.  Next: run.bat  (first time: extract.bat and ingest.bat before it)
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
TS=$(date +%F-%H%M)

echo "== backup of the current version: ~/chatbot-backup-$TS.tar.gz"
tar -czf ~/chatbot-backup-$TS.tar.gz --exclude venv --exclude data/models --exclude data/logs .

echo "== new code (old files that are no longer used are removed)"
rm -f chatlog.py
tar -xzf /tmp/chatbot-code.tar.gz -C ~/chatbot
rm -f /tmp/chatbot-code.tar.gz

echo "== Python packages"
~/chatbot/venv/bin/pip install -q -r requirements.txt < /dev/null

echo "== settings (.env) - other lines such as ALLOWED_ORIGINS are kept"
sed -i 's/\r$//' .env
setv() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
setv AWS_REGION ap-south-1
setv LLM_MODEL apac.amazon.nova-lite-v1:0
setv LLM_FALLBACK_MODEL none
setv TEMPERATURE 0
setv MAX_ANSWER_TOKENS 600
setv ANSWER_WORDS 80
setv LLM_TIMEOUT 60
setv LLM_MAX_CONCURRENCY 200
setv REWRITE_FOLLOWUPS true
setv MIN_SCORE 0.52
setv TOP_K 12
setv MAX_PER_PAGE 2
setv MAX_CONTEXT_CHARS 6500
# settings from earlier versions that are no longer used
sed -i -E '/^(GROQ_[A-Z_]*|LLM_PROVIDER|BEDROCK_REGION|REASONING_EFFORT|LOCAL_THINKING|RERANK[A-Z_]*|CACHE_MINUTES|FOLLOW_UPS|TRUST_PROXY|ADMIN_TOKEN|LOG_DIR|LOG_DAYS)=/d' .env
chmod 600 .env
grep -q "^AWS_ACCESS_KEY_ID=" .env || echo "WARNING: AWS keys missing in ~/chatbot/.env - see README (send-keys step)"

echo "== removing old stored chat logs"
rm -rf ~/chatbot/data/logs

echo "== service (same port 8002, local only, no access log)"
sudo tee /etc/systemd/system/chatbot.service > /dev/null <<'UNIT'
[Unit]
Description=eChipHub Assistant
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/chatbot
ExecStart=/home/ubuntu/chatbot/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8002 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
Restart=always
RestartSec=5
CPUQuota=200%
CPUWeight=20
MemoryMax=1500M
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable chatbot > /dev/null 2>&1 || true

if systemctl list-unit-files 2>/dev/null | grep -q '^ollama.service'; then
  echo "== the local model is no longer used: stopping Ollama (frees about 4 CPUs and 5 GB RAM)"
  sudo systemctl disable --now ollama > /dev/null 2>&1 || true
fi

echo "== Nginx for chat-test.echiphub.in: answer timeout 300 s, no access log"
F=/etc/nginx/sites-available/chatbot
sudo cp "$F" /tmp/chatbot-nginx.bak
sudo sed -i 's/proxy_read_timeout [0-9]*s;/proxy_read_timeout 300s;/' "$F"
grep -q "access_log off;" "$F" || sudo sed -i 's/server_name chat-test.echiphub.in;/server_name chat-test.echiphub.in;\n    access_log off;/' "$F"
if sudo nginx -t > /dev/null 2>&1; then
  sudo systemctl reload nginx
  echo "Nginx OK"
else
  sudo cp /tmp/chatbot-nginx.bak "$F"
  echo "Nginx test failed - the previous Nginx file was restored, nothing changed"
fi
echo "== done"
}
main