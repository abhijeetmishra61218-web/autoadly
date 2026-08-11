# check_ad.py
import asyncio
import aiosqlite
import database as db

async def check():
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM advertisements")
        rows = await cursor.fetchall()
        for row in rows:
            print(dict(row))

asyncio.run(check())