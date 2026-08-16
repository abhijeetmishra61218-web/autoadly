"""
Loads a raw Telethon .session file, verifies it's alive, sets a 2FA password
(CRITICAL — locks out the seller or anyone else with a copy of this file),
and prints the StringSession to add to your bot's ad_accounts table.

Usage:
    python3 convert_and_secure.py telethon_918899944649.session
"""

import sys
import asyncio
from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

async def main(session_file):
    session_name = session_file.replace(".session", "")
    client = TelegramClient(SQLiteSession(session_name), API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print(f"❌ {session_file}: NOT authorized — this session is dead/logged out. Do not use it.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"✅ {session_file} is ALIVE")
    print(f"   Logged in as: {me.first_name or ''} (@{me.username or 'no username'})")
    print(f"   Phone: {me.phone}")
    print(f"   User ID: {me.id}")

    # ---- Set 2FA password NOW, before anyone else can ----
    new_password = input(f"\nSet a NEW 2FA password for this account right now (required): ").strip()
    if new_password:
        try:
            await client.edit_2fa(new_password=new_password)
            print("✅ 2FA password set — this account is now locked to you.")
        except Exception as e:
            print(f"⚠️  Could not set 2FA: {e}")
            print("   (If it already has a 2FA password from the seller, this account may not be fully yours. Be cautious.)")
    else:
        print("⚠️  Skipped setting 2FA — do this manually ASAP, or the seller could lock you out.")

    # ---- Export as StringSession for your bot ----
    string_session = StringSession.save(client.session)
    print(f"\n=== StringSession for {me.phone} ===")
    print(string_session)
    print("=== end ===\n")

    await client.disconnect()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 convert_and_secure.py <session_file>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
