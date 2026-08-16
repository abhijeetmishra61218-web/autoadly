"""
Checks directly (via the ad account's own session) whether a specific message
still exists in a given chat, and prints the raw recent message history so we
can see what's actually there right now.

Usage:
    python3 check_message.py <ad_account_id> <chat_username> <message_id>

Example:
    python3 check_message.py 8 OFMManiacs 1031099
"""

import sys
import asyncio
import database as db
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

async def main(ad_account_id, chat_username, message_id):
    account = await db.get_ad_account_by_id(int(ad_account_id))
    if not account:
        print(f"No ad account with id={ad_account_id}")
        return

    client = TelegramClient(StringSession(account["session_string"]), API_ID, API_HASH)
    await client.connect()

    print(f"Checking message id={message_id} in @{chat_username} using account {account['phone']}...\n")

    msg = await client.get_messages(chat_username, ids=int(message_id))
    if msg is None:
        print(f"❌ Message {message_id} does NOT exist in @{chat_username} right now (deleted, or never existed at this id).")
    else:
        print(f"✅ Message {message_id} DOES exist:")
        print(f"   Text: {msg.text[:200] if msg.text else '(no text)'}")
        print(f"   Date: {msg.date}")

    print("\n--- Last 10 messages actually in this chat right now ---")
    async for m in client.iter_messages(chat_username, limit=10):
        preview = (m.text or "(no text)")[:60].replace("\n", " ")
        print(f"  id={m.id}  date={m.date}  {preview}")

    await client.disconnect()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 check_message.py <ad_account_id> <chat_username> <message_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
