#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "payments_flow.py" ] || [ ! -f "flow_state.py" ]; then
  echo "payments_flow.py / flow_state.py not found in $PROJECT_DIR — run this from inside the deploy_autoscan_fix folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current files"
cp payments_flow.py "payments_flow.py.bak_$TS"
cp flow_state.py "flow_state.py.bak_$TS"

echo "Installing patched payments_flow.py and flow_state.py"
cp deploy_autoscan_fix/payments_flow.py payments_flow.py
cp deploy_autoscan_fix/flow_state.py flow_state.py

echo "Running cleanup"
bash deploy_autoscan_fix/cleanup_clutter.sh

echo "Sanity-compiling changed files"
python3 -m py_compile payments_flow.py flow_state.py

echo "Restarting service"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo
echo "Done. Backups saved as payments_flow.py.bak_$TS and flow_state.py.bak_$TS"
