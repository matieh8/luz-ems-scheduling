#!/bin/bash
# Staging server: separate database, separate ports, demo mode by default.
# Runs side by side with the live server on the same machine.
set -e
cd "$(dirname "$0")"
[ -f .env.staging ] && set -a && source .env.staging && set +a
export LUZ_ENV="staging"
export LUZ_DATA_DIR="${LUZ_DATA_DIR:-data-staging}"
export WHATSAPP_BRIDGE_PORT="${WHATSAPP_BRIDGE_PORT:-8021}"
export LUZ_DISABLE_WHATSAPP_BRIDGE="${LUZ_DISABLE_WHATSAPP_BRIDGE:-1}"
source venv/bin/activate
if [ "$1" = "--demo-data" ]; then python scripts/seed_demo.py; fi
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8016}" --workers 1
