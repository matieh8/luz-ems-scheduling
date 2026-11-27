#!/bin/bash
# Live server. Reads .env if present.
set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a
# The staging copy (folder ending in _staging) is always staging, even when its service runs this script:
# its own label, its own WhatsApp bridge port, and no WhatsApp bridge unless asked for, so it can never
# send through the live WhatsApp number. Its database folder is left exactly as it is.
if [[ "$(pwd)" == *_staging ]]; then
  export LUZ_ENV=staging
  export WHATSAPP_BRIDGE_PORT=8021
  [ "${LUZ_STAGING_WHATSAPP:-0}" = "1" ] || export LUZ_DISABLE_WHATSAPP_BRIDGE=1
fi
export LUZ_ENV="${LUZ_ENV:-live}"
export LUZ_DATA_DIR="${LUZ_DATA_DIR:-data}"
export WHATSAPP_BRIDGE_PORT="${WHATSAPP_BRIDGE_PORT:-8020}"
# WhatsApp Web bridge: install its Node dependencies once, if Node is available.
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && [ ! -d backend/whatsapp/node_modules ] && [ "${LUZ_DISABLE_WHATSAPP_BRIDGE:-0}" != "1" ]; then
  echo "[whatsapp-bridge] installing Node dependencies (first run)..."
  (cd backend/whatsapp && npm install --omit=dev --no-audit --no-fund) || echo "[whatsapp-bridge] npm install failed; WhatsApp Web will be unavailable"
fi
source venv/bin/activate
# Only nginx (on this machine) may reach the app; the port is never open to the internet directly.
exec uvicorn backend.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8015}" --workers 1
