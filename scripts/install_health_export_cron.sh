#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIPELINE="$ROOT/scripts/run_whatsapp_health_pipeline.sh"
MARKER="# health-agent-bridge-whatsapp-export"

chmod +x "$PIPELINE" "$ROOT/scripts/install_health_export_cron.sh"

LOG_DIR="$ROOT/storage/logs"
mkdir -p "$LOG_DIR"
REMINDER_LOG="$LOG_DIR/health-export-reminder.log"
PIPELINE_LOG="$LOG_DIR/health-export-pipeline.log"

TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARKER" >"$TMP" || true
{
  cat "$TMP"
  echo "30 18 * * * $PIPELINE reminder >>$REMINDER_LOG 2>&1 $MARKER"
  echo "0 19 * * * $PIPELINE download-sync >>$PIPELINE_LOG 2>&1 $MARKER"
} >"$TMP.new"
crontab "$TMP.new"
rm -f "$TMP" "$TMP.new"

echo "Cron instalado:"
echo "  18:30 -> recordatorio export Apple Health"
echo "  19:00 -> descarga WhatsApp Web + import incremental + summary"
crontab -l | grep "$MARKER" || true
