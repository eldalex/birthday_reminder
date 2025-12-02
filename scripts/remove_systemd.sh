#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="bd-reminder"

echo "==> Stopping and disabling service $SERVICE_NAME"
sudo systemctl stop "$SERVICE_NAME" || true
sudo systemctl disable "$SERVICE_NAME" || true

UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ -f "$UNIT_FILE" ]]; then
  echo "==> Removing unit file $UNIT_FILE"
  sudo rm -f "$UNIT_FILE"
fi

echo "==> Reloading systemd"
sudo systemctl daemon-reload

echo "==> Done. To remove venv and files, delete the project directory manually."

