#!/bin/bash
# Live server. Reads .env if present.
set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a
export LUZ_ENV="${LUZ_ENV:-live}"
export LUZ_DATA_DIR="${LUZ_DATA_DIR:-data}"
export WHATSAPP_BRIDGE_PORT="${WHATSAPP_BRIDGE_PORT:-8020}"
# WhatsApp Web bridge: install its Node dependencies once, if Node is available.
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 && [ ! -d backend/whatsapp/node_modules ] && [ "${LUZ_DISABLE_WHATSAPP_BRIDGE:-0}" != "1" ]; then
  echo "[whatsapp-bridge] installing Node dependencies (first run)..."
  (cd backend/whatsapp && npm install --omit=dev --no-audit --no-fund) || echo "[whatsapp-bridge] npm install failed; WhatsApp Web will be unavailable"
fi
source venv/bin/activate
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8015}" --workers 1
