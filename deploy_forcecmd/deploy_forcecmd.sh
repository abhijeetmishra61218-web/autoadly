#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "admin_commands.py" ] || [ ! -f "content_store.py" ]; then
  echo "admin_commands.py / content_store.py not found in $PROJECT_DIR — run this from inside the deploy_forcecmd folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current files"
cp admin_commands.py "admin_commands.py.bak_$TS"
cp content_store.py "content_store.py.bak_$TS"

echo "Installing patched files"
cp deploy_forcecmd/admin_commands.py admin_commands.py
cp deploy_forcecmd/content_store.py content_store.py

echo "Sanity-compiling"
python3 -m py_compile admin_commands.py content_store.py

echo "Restarting service"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo
echo "Done. Backups saved as admin_commands.py.bak_$TS and content_store.py.bak_$TS"
