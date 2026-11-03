#!/bin/bash
set -e
APP_DIR="/home/ubuntu/luz_ems_scheduling"
BRANCH="main"

cd "$APP_DIR"

# Pull latest code
git fetch origin
git reset --hard "origin/$BRANCH"

# Update Python dependencies
source venv/bin/activate
pip install -r requirements.txt

# Update Node dependencies for WhatsApp Web bridge
if [ -d backend/whatsapp ]; then
    cd backend/whatsapp
    npm install
    cd "$APP_DIR"
fi

# Restart service
sudo systemctl restart luz-ems.service

# Verify health
sleep 3
if curl -fsS http://127.0.0.1:8015/api/health > /dev/null; then
    echo "Deploy successful. Health check passed."
else
    echo "Deploy failed. Health check failed."
    exit 1
fi
