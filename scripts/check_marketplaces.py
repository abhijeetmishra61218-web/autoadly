# check_marketplaces.py
import asyncio
import aiosqlite
import database as db

async def check():
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        print("--- marketplaces ---")
        cursor = await conn.execute("SELECT * FROM marketplaces")
        for row in await cursor.fetchall():
            print(dict(row))
        print("--- marketplace_list_items ---")
        cursor = await conn.execute("SELECT * FROM marketplace_list_items")
        for row in await cursor.fetchall():
            print(dict(row))

asyncio.run(check())