#!/usr/bin/env bash
# SQLite log veritabanının tutarlı bir kopyasını alır, son 30 yedeği saklar.
# Cron (chatbot kullanıcısı):  15 3 * * * /opt/chatbot/deploy/backup.sh
# Yedekleri sunucu dışına almak için: scp/rsync ile data/backups/ dizinini çek.
set -euo pipefail

APP_DIR=/opt/chatbot
DB="$APP_DIR/data/chatbot.db"
OUT_DIR="$APP_DIR/data/backups"
KEEP=30

mkdir -p "$OUT_DIR"
target="$OUT_DIR/chatbot-$(date +%Y%m%d-%H%M%S).db"

# sqlite3 CLI gerektirmesin diye Python'un backup API'si kullanılıyor.
"$APP_DIR/.venv/bin/python" - "$DB" "$target" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
EOF

ls -1t "$OUT_DIR"/chatbot-*.db | tail -n +$((KEEP + 1)) | xargs -r rm --
echo "Yedek: $target"
