#!/usr/bin/env bash
# Sichert die Bot-Datenbank nach backups/ (läuft täglich per cron, siehe install.sh).
# Backups älter als 14 Tage werden gelöscht.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="$APP_DIR/data/mancave.db"
mkdir -p "$APP_DIR/backups"

if [ -f "$DB" ]; then
    # .backup ist sicher, auch während der Bot läuft
    sqlite3 "$DB" ".backup '$APP_DIR/backups/mancave-$(date +%F).db'"
fi
find "$APP_DIR/backups" -name "mancave-*.db" -mtime +14 -delete
