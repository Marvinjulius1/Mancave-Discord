#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Installiert den Mancave-Bot als Dauer-Dienst (Ubuntu / Debian).
#
#   Aufruf im Repo-Ordner:   bash deploy/install.sh
#
# Was passiert:
#   - Python + Abhängigkeiten werden installiert (eigene .venv)
#   - systemd-Dienst "mancave-bot": startet beim Hochfahren, startet nach Absturz neu
#   - tägliches Datenbank-Backup um 03:30 Uhr (14 Tage aufbewahrt)
# Das Skript kann gefahrlos mehrfach ausgeführt werden.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
SERVICE=/etc/systemd/system/mancave-bot.service

echo "==> Installiere Systempakete ..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git sqlite3 >/dev/null

echo "==> Richte Python-Umgebung ein ..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi
chmod 600 "$APP_DIR/.env"
chmod +x "$APP_DIR/deploy/"*.sh

echo "==> Richte Dienst mancave-bot ein ..."
sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Mancave Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable mancave-bot >/dev/null 2>&1

echo "==> Richte tägliches Backup ein ..."
( crontab -l 2>/dev/null | grep -v "mancave-backup" || true
  echo "30 3 * * * $APP_DIR/deploy/backup.sh >/dev/null 2>&1 # mancave-backup" ) | crontab -

if grep -q "dein-bot-token-hier" "$APP_DIR/.env"; then
    echo
    echo "⚠️  Fast fertig! Trag jetzt Token und Server-ID ein:"
    echo "      nano $APP_DIR/.env"
    echo "    Danach starten mit:"
    echo "      sudo systemctl restart mancave-bot"
else
    sudo systemctl restart mancave-bot
    echo
    echo "✅ Bot läuft! Status:  sudo systemctl status mancave-bot"
    echo "   Live-Log:           journalctl -u mancave-bot -f"
fi
