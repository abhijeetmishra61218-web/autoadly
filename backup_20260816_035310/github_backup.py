"""
AutoAdly - Full project backup (code + data) to a private GitHub repo,
every 10 minutes. Complements the Telegram zip backup — this one lets a
fresh RDP get back to fully working with a single `git clone`.
"""

import os
import asyncio
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, ".git_token")
REPO_URL = "github.com/abhijeetmishra61218-web/autoadly.git"

BACKUP_INTERVAL_SECONDS = 15 * 60

def _run(cmd):
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)

def _get_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            return f.read().strip()
    except Exception:
        return None

def do_backup():
    token = _get_token()
    if not token:
        print("[github_backup] No .git_token file found — skipping.")
        return

    add_result = _run(["git", "add", "-A"])
    if add_result.returncode != 0:
        print(f"[github_backup] git add failed: {add_result.stderr}")
        return

    status_result = _run(["git", "status", "--porcelain"])
    if not status_result.stdout.strip():
        return  # nothing changed, skip commit/push entirely

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_result = _run(["git", "commit", "-m", f"Auto backup {timestamp}"])
    if commit_result.returncode != 0:
        print(f"[github_backup] git commit failed: {commit_result.stderr}")
        return

    push_url = f"https://abhijeetmishra61218-web:{token}@{REPO_URL}"
    push_result = _run(["git", "push", push_url, "main"])
    if push_result.returncode != 0:
        print(f"[github_backup] git push failed: {push_result.stderr}")
        return

    print(f"[github_backup] Pushed successfully at {timestamp}")

async def backup_loop():
    while True:
        try:
            await asyncio.to_thread(do_backup)
        except Exception as e:
            print(f"[github_backup] loop error: {e}")
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
