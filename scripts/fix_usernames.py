import asyncio
import aiosqlite
from telethon import TelegramClient
from telethon.sessions import StringSession
import database as db

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

async def fix_usernames():
    account = await db.get_ad_account_by_id(1)
    client = TelegramClient(StringSession(account["session_string"]), API_ID, API_HASH)
    await client.connect()

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM marketplaces")
        marketplaces = await cursor.fetchall()

        fixed = 0
        for m in marketplaces:
            try:
                entity = await client.get_entity(m["chat_id"])
                real_username = getattr(entity, "username", None)
                if real_username and real_username != m["chat_username"]:
                    await conn.execute("UPDATE marketplaces SET chat_username = ? WHERE id = ?", (real_username, m["id"]))
                    print(f"Fixed id={m['id']}: {m['chat_username']!r} -> {real_username!r}")
                    fixed += 1
            except Exception as e:
                print(f"Could not resolve id={m['id']} ({m['chat_username']}): {e}")
        await conn.commit()
    await client.disconnect()
    print(f"Done. Fixed {fixed} stale username(s).")

asyncio.run(fix_usernames())
