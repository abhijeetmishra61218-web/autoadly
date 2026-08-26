"""
Keeps ad_bot.db's post_logs table tiny (so it never slows down regular
bot responses) while preserving full history in Google Sheets.

Every 15 min: push whatever's accumulated in post_logs to the "PostLogs"
Sheet tab, then delete those rows locally.

Every 6h: trim the Sheet itself so it doesn't grow forever - kept 1h wider
than /alog's 6h window (see admin_commands.py) so /alog always has full
coverage even mid-trim.
"""

import asyncio

import database as db
import sheets_store

SYNC_INTERVAL_SECONDS = 15 * 60
TRIM_INTERVAL_SECONDS = 6 * 60 * 60
SHEET_RETENTION_HOURS = 7  # 6h /alog window + 1h safety margin


async def sync_loop():
    while True:
        try:
            rows = await db.get_post_logs_for_sync()
            if rows:
                sheet_rows = [
                    {
                        "posted_at": r["posted_at"],
                        "ad_account_id": r["ad_account_id"],
                        "marketplace_id": r["marketplace_id"],
                        "chat_username": r["chat_username"],
                        "message_link": r["message_link"],
                    }
                    for r in rows
                ]
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, sheets_store.append_post_logs, sheet_rows)
                await db.delete_post_logs_by_ids([r["id"] for r in rows])
                print(f"[logs_sync] Synced {len(rows)} post_logs rows to Sheets and cleared them locally.")
        except sheets_store.SheetsUnavailableError as e:
            print(f"[logs_sync] Sheets unavailable ({e}) - leaving rows local for next attempt.")
        except Exception as e:
            print(f"[logs_sync] Sync run failed: {e}")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


async def trim_loop():
    while True:
        await asyncio.sleep(TRIM_INTERVAL_SECONDS)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, sheets_store.trim_post_logs, SHEET_RETENTION_HOURS)
            print(f"[logs_sync] Trimmed Sheets PostLogs older than {SHEET_RETENTION_HOURS}h.")
        except sheets_store.SheetsUnavailableError as e:
            print(f"[logs_sync] Sheets unavailable for trim ({e}).")
        except Exception as e:
            print(f"[logs_sync] Trim run failed: {e}")
