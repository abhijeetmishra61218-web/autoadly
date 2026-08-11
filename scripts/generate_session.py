# generate_session.py
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

API_ID = 37701222      # same values as engine.py
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\nYour session string (save this):\n")
    print(client.session.save())