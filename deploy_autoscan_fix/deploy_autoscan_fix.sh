#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "payments_flow.py" ]; then
  echo "payments_flow.py not found in $PROJECT_DIR — run this from inside the deploy_autoscan_fix folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current payments_flow.py to payments_flow.py.bak_$TS"
cp payments_flow.py "payments_flow.py.bak_$TS"

echo "Installing patched payments_flow.py"
cp deploy_autoscan_fix/payments_flow.py payments_flow.py

echo "Restarting service"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo "Done. Backup saved as payments_flow.py.bak_$TS"
