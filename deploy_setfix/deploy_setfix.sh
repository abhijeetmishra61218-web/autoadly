#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "adwizard.py" ]; then
  echo "adwizard.py not found in $PROJECT_DIR — run this from inside the deploy_setfix folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current adwizard.py to adwizard.py.bak_$TS"
cp adwizard.py "adwizard.py.bak_$TS"

echo "Installing patched adwizard.py"
cp deploy_setfix/adwizard.py adwizard.py

echo "Sanity-compiling"
python3 -m py_compile adwizard.py

echo "Restarting service"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo
echo "Done. Backup saved as adwizard.py.bak_$TS"
