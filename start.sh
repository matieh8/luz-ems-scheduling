#!/bin/bash
# Live server. Reads .env if present.
set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && source .env && set +a
export LUZ_ENV="${LUZ_ENV:-live}"
export LUZ_DATA_DIR="${LUZ_DATA_DIR:-data}"
export WHATSAPP_BRIDGE_PORT="${WHATSAPP_BRIDGE_PORT:-8020}"
source venv/bin/activate
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8015}" --workers 1
