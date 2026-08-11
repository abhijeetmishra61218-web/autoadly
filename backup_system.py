"""
AutoAdly - Daily backup: zips every critical file and sends it to the owner's
Telegram (Saved Messages) so nothing is lost when the RDP is wiped/changed.
Also cleans up old disposable data (post_logs, used_hashes) to keep storage sane.
"""

import os
import zipfile
import time
from datetime import datetime
from aiogram import Bot

import content_store as store
import database as db
import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(BASE_DIR, "_backups")

# Everything here is critical and irreplaceable if lost
CRITICAL_FILES = [
    "ad_bot.db",              # all ad accounts (session strings!), marketplaces, ads, logs
    "settings.json",
    "plans.json",
    "action_emojis.json",
    "admins.json",
    "users.json",
    "subscriptions.json",
    "customer_adbots.json",
    "banned.json",
    "cryptos.json",
    "used_hashes.json",
    "pending_account_requests.json",
]

LOG_RETENTION_SECONDS = 24 * 60 * 60  # keep only last 24h of post_logs — recent activity only, not historical
USED_HASH_RETENTION_DAYS = 90         # keep 90 days of used payment hashes (long enough to block replay attempts, short enough not to grow forever)

async def cleanup_old_data():
    """Removes disposable data that's safe to lose, to keep the backup small and storage sane."""
    import aiosqlite
    cutoff = time.time() - LOG_RETENTION_SECONDS
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM post_logs WHERE posted_at < ?", (cutoff,))
        await conn.commit()
    print("[backup] Cleaned old post_logs older than 24h.")

def make_backup_zip():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zip_path = os.path.join(BACKUP_DIR, f"autoadly_backup_{timestamp}.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in CRITICAL_FILES:
            fpath = os.path.join(BASE_DIR, fname)
            if os.path.exists(fpath):
                zf.write(fpath, arcname=fname)

    return zip_path

async def run_daily_backup():
    await cleanup_old_data()
    zip_path = make_backup_zip()
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)

    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if not owner_id:
        print("[backup] No owner_id set yet — skipping send, zip saved locally only.")
        return

    bot = Bot(token=config.BOT_TOKEN)
    try:
        from aiogram.types import FSInputFile
        file = FSInputFile(zip_path)
        await bot.send_document(
            owner_id, file,
            caption=f"AutoAdly daily backup — {datetime.now().strftime('%Y-%m-%d %H:%M')} ({size_mb:.1f} MB)\n\nKeep this safe — it contains all Ad Bot Account sessions and customer data."
        )
        print(f"[backup] Sent successfully: {zip_path}")
    except Exception as e:
        print(f"[backup] Failed to send backup: {e}")
    finally:
        await bot.session.close()

    # Keep only the last 3 local zips so disk doesn't fill up with old backups
    all_backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith("autoadly_backup_")]
    )
    for old_backup in all_backups[:-3]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
        except Exception:
            pass

async def cleanup_loop():
    """Runs the disposable-data cleanup once daily, forever.
    No longer sends a Telegram zip — GitHub backup (github_backup.py)
    now covers full data + code backup instead."""
    import asyncio
    while True:
        try:
            await cleanup_old_data()
        except Exception as e:
            print(f"[backup] Cleanup run failed: {e}")
        await asyncio.sleep(24 * 60 * 60)
