#!/usr/bin/env bash
# Holt die neueste Version von GitHub und startet den Bot neu.
#   Aufruf:  bash deploy/update.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

"$APP_DIR/deploy/backup.sh"
git pull --ff-only
"$APP_DIR/.venv/bin/pip" install -q -r requirements.txt
sudo systemctl restart mancave-bot
echo "✅ Aktualisiert: $(git log --oneline -1)"
