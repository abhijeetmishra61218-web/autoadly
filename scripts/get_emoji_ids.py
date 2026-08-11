"""
Run this ONCE to get custom emoji document IDs.
1. Send a message using the custom animated emojis you want, in Saved Messages
2. Run: python3 get_emoji_ids.py
3. Copy the document_id values you need
"""
from telethon import TelegramClient
from telethon.tl.types import MessageEntityCustomEmoji

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"
SESSION_STRING = "PASTE_ANY_ACCOUNT_SESSION_STRING_HERE"  # can reuse your dummy account's session
CHAT = "me"
LIMIT = 20

from telethon.sync import TelegramClient as SyncClient
from telethon.sessions import StringSession

with SyncClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
    print(f"Connected! Scanning your last {LIMIT} messages in Saved Messages")
    print("-" * 50)
    for msg in client.iter_messages(CHAT, limit=LIMIT):
        if not msg.entities:
            continue
        for ent in msg.entities:
            if isinstance(ent, MessageEntityCustomEmoji):
                emoji_char = msg.text[ent.offset: ent.offset + ent.length]
                print(f"Emoji: {emoji_char}  ->  document_id: {ent.document_id}")
