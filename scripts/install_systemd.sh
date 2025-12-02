#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="bd-reminder"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
ENV_FILE="$PROJECT_DIR/.env"

echo "==> Project dir: $PROJECT_DIR"

if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "requirements.txt not found at $REQUIREMENTS" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Creating $ENV_FILE from .env.example (edit it!)"
  cp "$PROJECT_DIR/.env.example" "$ENV_FILE" || true
fi

echo "==> Creating virtualenv and installing deps"
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$REQUIREMENTS"

# Detect entrypoint
ENTRYPOINT=""
if [[ -f "$PROJECT_DIR/bot/main.py" ]]; then
  ENTRYPOINT="$PROJECT_DIR/bot/main.py"
elif [[ -f "$PROJECT_DIR/main.py" ]]; then
  ENTRYPOINT="$PROJECT_DIR/main.py"
else
  echo "Cannot find entrypoint (bot/main.py or main.py) in $PROJECT_DIR" >&2
  exit 1
fi

USER_NAME="${SUDO_USER:-$USER}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "==> Writing systemd unit to $UNIT_FILE (sudo required)"
sudo tee "$UNIT_FILE" >/dev/null <<UNIT
[Unit]
Description=Birthday Reminder Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON_BIN $ENTRYPOINT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

echo "==> Reloading systemd, enabling and starting service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "==> Done. Check status and logs:"
echo "    sudo systemctl status $SERVICE_NAME"
echo "    sudo journalctl -u $SERVICE_NAME -n 200 -f"

