#!/bin/bash
set -e
cd "$(dirname "$0")"
source venv/bin/activate
exec uvicorn backend.main:app --host 0.0.0.0 --port 8015 --workers 1
