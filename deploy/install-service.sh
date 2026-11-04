#!/bin/bash
# Installs LUZ EMS as a systemd service so it runs permanently, restarts on crash and starts on reboot.
# Run once on the server, from the repo folder:  sudo ./deploy/install-service.sh
set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_USER="${SUDO_USER:-$(whoami)}"
UNIT=/etc/systemd/system/luz-ems.service
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__USER__|$RUN_USER|g" "$APP_DIR/deploy/luz-ems.service" > "$UNIT"
chmod +x "$APP_DIR/start.sh"
systemctl daemon-reload
systemctl enable luz-ems
systemctl restart luz-ems
sleep 3
systemctl --no-pager --lines=15 status luz-ems || true
echo
echo "Installed. Useful commands:"
echo "  sudo systemctl restart luz-ems     # after git pull"
echo "  sudo journalctl -u luz-ems -f      # live logs (incl. [whatsapp-bridge] lines)"
