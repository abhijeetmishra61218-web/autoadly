#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "database.py" ] || [ ! -f "engine.py" ] || [ ! -f "admin_commands.py" ]; then
  echo "database.py / engine.py / admin_commands.py not found in $PROJECT_DIR — run this from inside the deploy_realstats folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current files"
cp database.py "database.py.bak_$TS"
cp engine.py "engine.py.bak_$TS"
cp admin_commands.py "admin_commands.py.bak_$TS"

echo "Installing patched files"
cp deploy_realstats/database.py database.py
cp deploy_realstats/engine.py engine.py
cp deploy_realstats/admin_commands.py admin_commands.py

echo "Sanity-compiling"
python3 -m py_compile database.py engine.py admin_commands.py

echo "Restarting service (new tables get created automatically on startup via init_db)"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo
echo "Done. Backups saved as database.py.bak_$TS, engine.py.bak_$TS, admin_commands.py.bak_$TS"
echo "NOTE: the two new stats tables start EMPTY — totals accumulate from now on,"
echo "nothing historical is backfilled."
