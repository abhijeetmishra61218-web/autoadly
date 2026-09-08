"""
Logs into the account stored in ad_bot.db as phone '+10000000000' (id=1),
using the Telethon session_string already saved for it — no OTP needed
as long as that session hasn't been revoked by Telegram.
"""

import sqlite3
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Same values used elsewhere in the project (engine.py / generate_session.py)
API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

DB_PATH = "ad_bot.db"
TARGET_PHONE = "+10000000000"  # the placeholder number for the account in question

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, phone, session_string, status, two_step_password FROM ad_accounts WHERE phone = ?", (TARGET_PHONE,))
    row = cur.fetchone()
    conn.close()

    if not row:
        print(f"No row found for phone {TARGET_PHONE}")
        return

    acc_id, phone, session_string, status, two_step_password = row
    print(f"Found account id={acc_id}, phone={phone}, status={status}")

    with TelegramClient(StringSession(session_string), API_ID, API_HASH) as client:
        me = client.get_me()
        print(f"\nLogged in successfully as: {me.first_name} (@{me.username}), id={me.id}, phone on Telegram={me.phone}")
        print("\nYou can now use `client` to fetch dialogs, forum links, etc.")
        for d in list(client.iter_dialogs(limit=10)):
            print(" -", d.name)

if __name__ == "__main__":
    main()
