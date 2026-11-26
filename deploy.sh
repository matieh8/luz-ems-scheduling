#!/bin/bash
# Deploys this checkout. The same file serves both servers, picked by the folder it lives in:
#   /home/ubuntu/luz_ems_scheduling          -> live    (branch main,    luz-ems.service,         port 8015)
#   /home/ubuntu/luz_ems_scheduling_staging  -> staging (branch staging, luz-ems-staging.service, port 8016)
# If the new version doesn't come up healthy, the previous version is put back.
# (A database backup is made by the app itself before any schema change, see backend/migrate.py.)
set -e

healthy() {
    for _ in $(seq 1 15); do
        curl -fsS "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1 && return 0
        sleep 2
    done
    return 1
}

install_and_restart() {
    source venv/bin/activate
    pip install -r requirements.txt
    if [ -d backend/whatsapp ]; then
        (cd backend/whatsapp && npm install)
    fi
    sudo systemctl restart "$SERVICE"
}

main() {
    APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ "$APP_DIR" == *_staging ]]; then
        BRANCH=staging; SERVICE=luz-ems-staging.service; PORT=8016
    else
        BRANCH=main; SERVICE=luz-ems.service; PORT=8015
    fi
    export PATH="/home/ubuntu/.local/bin:$PATH"
    cd "$APP_DIR"

    PREV="$(git rev-parse HEAD)"
    git fetch origin
    git reset --hard "origin/$BRANCH"
    if install_and_restart && healthy; then
        echo "Deploy successful ($BRANCH $(git rev-parse --short HEAD)). Health check passed."
        exit 0
    fi

    echo "Health check failed. Rolling back to $PREV."
    git reset --hard "$PREV"
    if install_and_restart && healthy; then
        echo "Rolled back: the previous version is running again."
    else
        echo "Rollback health check failed too. Check: sudo journalctl -u $SERVICE -n 100"
    fi
    exit 1
}

# Everything runs from main(), which bash reads in full before starting,
# so "git reset" rewriting this file mid-deploy can't change what runs.
main "$@"
