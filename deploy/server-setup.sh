#!/usr/bin/env bash
# Runs ON THE SERVER (deploy.ps1 calls it for you). Safe to run again and again.
# 1) copies the uploaded code to /opt/chatbot   2) installs Python packages
# 3) runs the bot as a service on 127.0.0.1:8000 4) makes it reachable at  <your-site>/chatbot/
set -euo pipefail

SITE_URL="${1:-http://13.235.238.82}"
APP=/opt/chatbot
NEW=/tmp/chatbot-new
RUN_USER=ubuntu

say() { echo; echo "==> $*"; }

# ---------------------------------------------------------------- 1. system packages
say "Checking Python on the server"
if ! python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  echo "ERROR: Python 3.10 or newer is needed on the server."; exit 1
fi
if ! python3 -c 'import ensurepip, venv' >/dev/null 2>&1 || ! command -v curl >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y -qq
  PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  apt-get install -y -qq python3-venv "python${PYV}-venv" curl || apt-get install -y -qq python3-venv curl
fi
python3 --version

# ---------------------------------------------------------------- 2. memory safety (small servers)
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if [ "$MEM_MB" -lt 2000 ] && [ "$(swapon --show | wc -l)" -eq 0 ]; then
  say "Small server (${MEM_MB} MB RAM) - adding 2 GB swap so it does not run out of memory"
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- 3. copy the new code
say "Copying the new code to $APP"
systemctl stop chatbot 2>/dev/null || true
mkdir -p "$APP"
cp -a "$NEW"/. "$APP"/
rm -rf "$NEW" /tmp/chatbot-upload.tar.gz
rm -f "$APP/data/qdrant/.lock"
mkdir -p "$APP/data/logs" "$APP/data/models"

# ---------------------------------------------------------------- 4. python packages
say "Installing Python packages (first time takes 2-4 minutes)"
[ -x "$APP/.venv/bin/python" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R "$RUN_USER:$RUN_USER" "$APP"

# ---------------------------------------------------------------- 5. the service
HOST="${SITE_URL#*://}"; HOST="${HOST%%/*}"
ORIGINS="http://$HOST,https://$HOST,http://13.235.238.82,https://13.235.238.82"
ORIGINS="$ORIGINS,https://echiphub.in,https://www.echiphub.in,https://events.echiphub.in,https://edx.echiphub.in"
ORIGINS="$ORIGINS,https://community.echiphub.in,https://labs.echiphub.in"

say "Creating the chatbot service"
cat > /etc/systemd/system/chatbot.service <<EOF
[Unit]
Description=eChipHub chatbot
After=network.target

[Service]
User=$RUN_USER
WorkingDirectory=$APP
Environment=TRUST_PROXY=true
Environment=QDRANT_PATH=$APP/data/qdrant
Environment=MODEL_DIR=$APP/data/models
Environment=LOG_DIR=$APP/data/logs
Environment=DATA_DIR=$APP/echiphub
Environment=ALLOWED_ORIGINS=$ORIGINS
ExecStart=$APP/.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable chatbot >/dev/null 2>&1
systemctl restart chatbot

# ---------------------------------------------------------------- 6. <site>/chatbot/  ->  127.0.0.1:8000
say "Connecting  /chatbot/  on the website to the bot"
if systemctl is-active --quiet apache2; then
  echo "Web server: Apache"
  if [ ! -f /etc/apache2/conf-enabled/chatbot.conf ]; then
    a2enmod proxy proxy_http >/dev/null
    cat > /etc/apache2/conf-available/chatbot.conf <<'EOF'
# eChipHub chatbot: everything under /chatbot/ goes to the bot on this server
ProxyPass        /chatbot/ http://127.0.0.1:8000/ flushpackets=on timeout=120
ProxyPassReverse /chatbot/ http://127.0.0.1:8000/
<Location /chatbot/>
    SetEnv no-gzip 1
</Location>
EOF
    a2enconf chatbot >/dev/null
    if apache2ctl configtest 2>/dev/null; then
      systemctl reload apache2; echo "Apache: /chatbot/ added"
    else
      a2disconf chatbot >/dev/null; systemctl reload apache2
      echo "ERROR: Apache did not accept the setting - undone, website untouched."
    fi
  else
    echo "Apache: /chatbot/ already set up"
  fi
elif systemctl is-active --quiet nginx; then
  echo "Web server: Nginx"
  cat > /etc/nginx/snippets/chatbot.conf <<'EOF'
# eChipHub chatbot: everything under /chatbot/ goes to the bot on this server
location /chatbot/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
EOF
  if ! grep -rqs "snippets/chatbot.conf" /etc/nginx/sites-enabled /etc/nginx/conf.d; then
    BK=/root/nginx-backup-$(date +%Y%m%d-%H%M%S); mkdir -p "$BK"; cp -aL /etc/nginx/sites-enabled /etc/nginx/conf.d "$BK"/ 2>/dev/null || true
    for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
      [ -f "$f" ] && grep -q "server_name" "$f" || continue
      sed -i --follow-symlinks '/^[[:space:]]*server_name/a\    include /etc/nginx/snippets/chatbot.conf;' "$f"
    done
    if nginx -t 2>/dev/null; then
      systemctl reload nginx; echo "Nginx: /chatbot/ added (backup in $BK)"
    else
      for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
        [ -f "$f" ] && sed -i --follow-symlinks '/snippets\/chatbot.conf/d' "$f"
      done
      systemctl reload nginx
      echo "ERROR: Nginx did not accept the setting - undone, website untouched."
    fi
  else
    echo "Nginx: /chatbot/ already set up"
  fi
else
  echo "WARNING: neither Apache nor Nginx is running on this server."
  echo "Port 80 is used by:"; ss -ltnp | grep -E ':80 |:443 ' || true
  echo "Send this output to Claude."
fi

# ---------------------------------------------------------------- 7. check
say "Waiting for the bot to start (loads the AI models, up to 2 minutes)"
for i in $(seq 1 60); do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health || true)
  [ "$CODE" = "200" ] && break
  sleep 2
done
echo "Bot directly    (127.0.0.1:8000/health): $(curl -s http://127.0.0.1:8000/health || echo 'NOT RUNNING')"
echo "Through website (localhost/chatbot/health): HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/chatbot/health || true)"
if [ "$CODE" != "200" ]; then
  echo; echo "Bot is not healthy yet. Last log lines:"; journalctl -u chatbot -n 25 --no-pager
fi
say "DONE"
