#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIPELINE="$ROOT/scripts/run_whatsapp_health_pipeline.sh"
MARKER="# health-agent-bridge-health-export"

chmod +x "$PIPELINE" "$ROOT/scripts/install_health_export_cron.sh"

LOG_DIR="$ROOT/storage/logs"
mkdir -p "$LOG_DIR"
REMINDER_LOG="$LOG_DIR/health-export-reminder.log"
PIPELINE_LOG="$LOG_DIR/health-export-pipeline.log"

TMP="$(mktemp)"
crontab -l 2>/dev/null | grep -v "$MARKER" >"$TMP" || true
{
  cat "$TMP"
  echo "30 18 * * * cd $ROOT && $PIPELINE reminder >>$REMINDER_LOG 2>&1 $MARKER"
  echo "0 19 * * * cd $ROOT && $PIPELINE download-sync >>$PIPELINE_LOG 2>&1 $MARKER"
  echo "15 19 * * * cd $ROOT && $PIPELINE download-sync >>$PIPELINE_LOG 2>&1 $MARKER"
  echo "30 19 * * * cd $ROOT && $PIPELINE download-sync >>$PIPELINE_LOG 2>&1 $MARKER"
  echo "45 19 * * * cd $ROOT && $PIPELINE download-sync >>$PIPELINE_LOG 2>&1 $MARKER"
} >"$TMP.new"
crontab "$TMP.new"
rm -f "$TMP" "$TMP.new"

echo "Cron instalado (America/Santiago en .env del pipeline):"
echo "  18:30 -> recordatorio Telegram"
echo "  19:00, 19:15, 19:30, 19:45 -> fetch ZIP Hermes + import + summary"
crontab -l | grep "$MARKER" || true
