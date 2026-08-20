#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "admin_commands.py" ]; then
  echo "admin_commands.py not found in $PROJECT_DIR — run this from inside the deploy_teststats folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current admin_commands.py"
cp admin_commands.py "admin_commands.py.bak_$TS"

echo "Installing patched admin_commands.py"
cp deploy_teststats/admin_commands.py admin_commands.py

echo "Sanity-compiling"
python3 -m py_compile admin_commands.py

echo "Restarting service"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo
echo "Done. Backup saved as admin_commands.py.bak_$TS"
