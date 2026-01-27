#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/opt/homelab-panel/trading-lab"
SYSTEMD_DIR="/etc/systemd/system"

install_unit() {
  local unit_file="$1"
  if [[ ! -f "$unit_file" ]]; then
    echo "Missing unit: $unit_file"
    return 0
  fi
  sudo cp "$unit_file" "$SYSTEMD_DIR/$(basename "$unit_file")"
}

install_unit "$ROOT_DIR/services/trading-lab-web.service"
install_unit "$ROOT_DIR/services/trading-lab-scheduler.service"
install_unit "$ROOT_DIR/services/alpaca-mcp.service"

sudo systemctl daemon-reload
sudo systemctl enable trading-lab-web.service trading-lab-scheduler.service || true
sudo systemctl restart trading-lab-web.service trading-lab-scheduler.service || true

if systemctl list-unit-files | grep -q alpaca-mcp.service; then
  sudo systemctl enable alpaca-mcp.service || true
  sudo systemctl restart alpaca-mcp.service || true
fi

echo "Services installed/updated."
