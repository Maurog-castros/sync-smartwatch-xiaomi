#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
if [[ -f "$ROOT/.env.server" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.server"
  set +a
fi
if [[ -z "${HEALTH_EXPORT_TELEGRAM_BOT_TOKEN:-}" && -f /home/mauro/Dev/hermes-openclaw-benchmark/.hermes/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /home/mauro/Dev/hermes-openclaw-benchmark/.hermes/.env
  set +a
  export HEALTH_EXPORT_TELEGRAM_BOT_TOKEN="${HEALTH_EXPORT_TELEGRAM_BOT_TOKEN:-${TELEGRAM_BOT_TOKEN:-}}"
  export HEALTH_EXPORT_TELEGRAM_CHAT_ID="${HEALTH_EXPORT_TELEGRAM_CHAT_ID:-8503943962}"
fi

export TZ="${HEALTH_BRIDGE_TIMEZONE:-America/Santiago}"
export PYTHONPATH="$ROOT/src"

PYTHON_BIN="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

MODE="${1:-download-sync}"
shift || true

case "$MODE" in
  reminder)
    exec "$PYTHON_BIN" "$ROOT/scripts/health_export_reminder.py" "$@"
    ;;
  download)
    if [[ "${HEALTH_EXPORT_SOURCE:-telegram}" == "telegram" ]]; then
      exec "$PYTHON_BIN" "$ROOT/scripts/telegram_fetch_export.py" "$@"
    fi
    exec "$PYTHON_BIN" "$ROOT/scripts/whatsapp_download_export.py" --headless "$@"
    ;;
  telegram-fetch)
    exec "$PYTHON_BIN" "$ROOT/scripts/telegram_fetch_export.py" "$@"
    ;;
  sync)
    if [[ -f "$ROOT/.env.server" ]] && command -v docker >/dev/null 2>&1; then
      exec docker run --rm --network openclaw_openclaw_net \
        --env-file "$ROOT/.env.server" \
        -v "$ROOT/src:/app/src:ro" \
        -v "$ROOT/scripts:/app/scripts:ro" \
        -v "$ROOT/storage:/app/storage" \
        -v "/home/mauro/Dev/openclaw-mauro/data/workspace/care/context:/care/context" \
        -e PYTHONPATH=/app/src \
        -e HEALTH_EXPORT_COVERAGE_CONTEXT_DIR=/care/context \
        sync-smartwatch-xiaomi-health-agent-bridge \
        python /app/scripts/sync_apple_health_export.py --refresh-summary "$@"
    else
      exec "$PYTHON_BIN" "$ROOT/scripts/sync_apple_health_export.py" --refresh-summary "$@"
    fi
    ;;
  download-sync)
    if [[ "${HEALTH_EXPORT_SOURCE:-telegram}" == "telegram" ]]; then
      DOWNLOAD_JSON="$("$PYTHON_BIN" "$ROOT/scripts/telegram_fetch_export.py" "$@")"
    else
      DOWNLOAD_JSON="$("$PYTHON_BIN" "$ROOT/scripts/whatsapp_download_export.py" --headless "$@")"
    fi
    printf '%s\n' "$DOWNLOAD_JSON"
    if "$PYTHON_BIN" -c "import json,sys; d=json.loads(sys.argv[1]); sys.exit(0 if d.get('downloaded') else 2)" "$DOWNLOAD_JSON"; then
      "$ROOT/scripts/run_whatsapp_health_pipeline.sh" sync "$@"
      exit $?
    fi
    echo '{"pipeline":"download-sync","sync_skipped":true,"reason":"no_new_whatsapp_file"}'
    ;;
  login)
    exec "$PYTHON_BIN" "$ROOT/scripts/whatsapp_download_export.py" --login "$@"
    ;;
  refresh-coverage)
    if [[ -f "$ROOT/.env.server" ]] && command -v docker >/dev/null 2>&1; then
      exec docker run --rm --network openclaw_openclaw_net \
        --env-file "$ROOT/.env.server" \
        -v "$ROOT/src:/app/src:ro" \
        -v "$ROOT/scripts:/app/scripts:ro" \
        -v "$ROOT/storage:/app/storage" \
        -v "/home/mauro/Dev/openclaw-mauro/data/workspace/care/context:/care/context" \
        -e PYTHONPATH=/app/src \
        -e HEALTH_EXPORT_COVERAGE_CONTEXT_DIR=/care/context \
        sync-smartwatch-xiaomi-health-agent-bridge \
        python /app/scripts/refresh_health_coverage.py "$@"
    fi
    exec "$PYTHON_BIN" "$ROOT/scripts/refresh_health_coverage.py" "$@"
    ;;
  *)
    echo "uso: $0 [reminder|download|sync|download-sync|refresh-coverage|login] [args...]" >&2
    exit 2
    ;;
esac
