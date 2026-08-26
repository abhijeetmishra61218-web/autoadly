#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)

if [ ! -f "sheets_store.py" ]; then
  echo "sheets_store.py not found in $PROJECT_DIR — run this from inside the deploy_sheetsfix folder that sits next to your bot files."
  exit 1
fi

echo "Backing up current sheets_store.py"
cp sheets_store.py "sheets_store.py.bak_$TS"

echo "Installing patched sheets_store.py (adds the missing 'import time')"
cp deploy_sheetsfix/sheets_store.py sheets_store.py

echo "Copying backfill_sheets.py in (not run automatically — see instructions after this)"
cp deploy_sheetsfix/backfill_sheets.py backfill_sheets.py

echo "Sanity-compiling"
python3 -m py_compile sheets_store.py backfill_sheets.py

echo "Restarting service"
sudo systemctl restart autoadly.service
sleep 2
sudo systemctl status autoadly.service --no-pager | head -15
echo
echo "Done. Backup saved as sheets_store.py.bak_$TS"
echo
echo "NEXT: run the one-time backfill manually (not run automatically, since it"
echo "overwrites the Sheet's Users/Subscriptions tabs):"
echo "    source .venv/bin/activate && python3 backfill_sheets.py"
