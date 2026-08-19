#!/bin/bash
# Deploy: backs up current files, drops in the patched ones, fixes ad #56,
# then tells you to restart the bot. Run from your project root
# (~/bot_project_clean) with the venv active.
set -e

TS=$(date +%Y%m%d_%H%M%S)

echo "== Backing up current files =="
cp ad_bot.db "ad_bot.db.bak_${TS}"
cp adwizard.py "adwizard.py.bak_${TS}"
cp engine.py "engine.py.bak_${TS}"
echo "  backups written with suffix .bak_${TS}"

echo "== Installing patched files =="
cp deploy_bundle/adwizard.py ./adwizard.py
cp deploy_bundle/engine.py ./engine.py
cp deploy_bundle/scripts/fix_ad56_list.py ./scripts/fix_ad56_list.py

echo "== Fixing @CyberGod's ad (id 56) =="
python3 scripts/fix_ad56_list.py

echo
echo "== Done. Now restart the bot process for the code changes to take effect. =="
echo "   If it's a systemd service:   sudo systemctl restart <your-service-name>"
echo "   If it's run_forever.sh in tmux/screen: reattach and Ctrl+C, then re-run run_forever.sh"
