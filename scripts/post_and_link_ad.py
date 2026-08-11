# post_and_link_ad.py
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import aiosqlite
import database as db

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"
SESSION_STRING = "1BVtsOLgBu2d_09lXu56BaCW9SOynMKCovdHXtzpsh1S39_T1RzIErXmEY9z0eudm_iMXM6fT2JNxdreAcZspLsRZ10g2sTAiu61XQy2IuGuiZF6bFluGxmKLv5Wbw1bEPkqwS1jlFZh_fAbQqAC0o314GQCNXo060L1YNrCA9aK9QCbRtKePiQSLYtpNr4ouCGu9298Ctx3FCQoVTY9kYP-EWsPkc3t1e8AqHoE7sNj0TZKnb-KOudCTaNEYGoHtkXETfPXYzOPJa-mWTvpRj06OaftbYklkYhkJdZHTKrQWPiUYMoAJ3eHV_80sBmPpG08nCqXG4hHky5PoDdhbLqsbUOKgI8c="

ANVESANA_CHAT_ID = -1001945309702

async def update_ad_source(chat_id: int, message_id: int):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE advertisements SET source_chat_id = ?, source_message_id = ?",
            (chat_id, message_id)
        )
        await conn.commit()

def main():
    with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        sent = client.send_message(ANVESANA_CHAT_ID, "🔥 TEST AD — Premium VPN & OTT Bundle 🔥")
        print(f"Sent message, ID = {sent.id}")
        asyncio.run(update_ad_source(ANVESANA_CHAT_ID, sent.id))
        print("Advertisement source updated in database.")

if __name__ == "__main__":
    main()