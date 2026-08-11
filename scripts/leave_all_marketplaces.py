"""
AutoAdly - Leaves every current marketplace across all ad accounts,
then wipes the local marketplace database so it can be rebuilt fresh
from a new chat-folder link.
"""

import asyncio
import aiosqlite
from telethon import TelegramClient
from telethon.sessions import StringSession
import database as db

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

async def leave_all_for_account(account):
    client = TelegramClient(StringSession(account["session_string"]), API_ID, API_HASH)
    await client.connect()

    left = 0
    failed = 0
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            try:
                await client.delete_dialog(dialog.entity)
                left += 1
                await asyncio.sleep(2)  # gentle pacing to avoid flood-waits during mass-leave
            except Exception as e:
                print(f"  Could not leave {dialog.name}: {e}")
                failed += 1

    await client.disconnect()
    print(f"[{account['phone']}] left {left} chat(s), {failed} failed.")

async def main():
    accounts = await db.get_all_ad_accounts()
    for account in accounts:
        await leave_all_for_account(account)

    # Wipe local marketplace records so we rebuild clean from the new folder
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM forum_topics")
        await conn.execute("DELETE FROM marketplace_list_items")
        await conn.execute("DELETE FROM marketplaces")
        await conn.commit()
    print("Cleared all local marketplace records.")

asyncio.run(main())
