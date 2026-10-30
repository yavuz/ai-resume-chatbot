#!/usr/bin/env bash
# Sunucuda güncelleme: sudo /opt/chatbot/deploy/deploy.sh
set -euo pipefail

APP_DIR=/opt/chatbot
APP_USER=chatbot

cd "$APP_DIR"
sudo -H -u "$APP_USER" git pull --ff-only
sudo -H -u "$APP_USER" .venv/bin/pip install --quiet -r requirements.txt
systemctl restart chatbot

for _ in $(seq 1 15); do
    if curl -fsS http://127.0.0.1:8000/healthz > /dev/null; then
        echo "OK: chatbot ayakta ($(git rev-parse --short HEAD))"
        exit 0
    fi
    sleep 1
done

echo "HATA: /healthz yanıt vermedi. Son loglar:" >&2
journalctl -u chatbot -n 50 --no-pager >&2
exit 1
