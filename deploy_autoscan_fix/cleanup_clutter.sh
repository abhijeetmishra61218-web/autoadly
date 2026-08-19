#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
TS=$(date +%Y%m%d_%H%M%S)
ARCHIVE="_old_backups_archive"

if [ ! -f "main.py" ]; then
  echo "main.py not found in $PROJECT_DIR — run this from inside the deploy_autoscan_fix folder that sits next to your bot files."
  exit 1
fi

mkdir -p "$ARCHIVE"

echo "Moving stray backup directories into $ARCHIVE/ ..."
for d in backup_before_* backup_2026* _backups deploy_bundle; do
  if [ -d "$d" ]; then
    echo "  $d"
    mv "$d" "$ARCHIVE/${d}_$TS" 2>/dev/null || true
  fi
done

echo "Moving stray zip files and root-level backup .py files into $ARCHIVE/ ..."
for f in *.zip backup_before_patch_*.py; do
  if [ -f "$f" ]; then
    echo "  $f"
    mv "$f" "$ARCHIVE/" 2>/dev/null || true
  fi
done

echo "Updating .gitignore so this stuff (and the sensitive files flagged separately) stop being swept into every auto-backup push"
GITIGNORE=".gitignore"
touch "$GITIGNORE"
add_line() {
  grep -qxF "$1" "$GITIGNORE" || echo "$1" >> "$GITIGNORE"
}
add_line "crash_log.txt"
add_line "$ARCHIVE/"
add_line "backup_before_*/"
add_line "backup_2026*/"
add_line "_backups/"
add_line "deploy_bundle*/"
add_line "*.zip"
add_line "__pycache__/"
add_line "*.pyc"
# Not deleted, not rotated — just stops NEW commits from including them.
# Secrets already in git history need rotation regardless (bot token,
# .session files, .git_token, API keys) — that's a separate step.
add_line "*.session"
add_line ".git_token"
add_line "config.py"

echo
echo "Done. Nothing was deleted — old backups/zips are sitting in $ARCHIVE/ if you ever need them."
echo "NOTE: adding config.py / *.session to .gitignore only stops FUTURE commits."
echo "If they were already pushed to GitHub before, they're still in that repo's history until rotated/purged."
