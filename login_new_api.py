"""
One-off login for a specific troublesome number, using a FRESH api_id/hash
instead of the bot's usual one - only matters for this login itself. Once
signed in, the resulting session_string works fine reconnecting under the
OLD api_id too (that's how Telethon/MTProto works - api_id only matters at
auth time), so nothing else in the bot needs to change. This adds the
account directly via database.add_ad_account, exactly like /addadbot does,
then kicks off the normal marketplace-join flow.
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError

import database as db
import account_setup

NEW_API_ID = 38226331
NEW_API_HASH = "ca1004923eb69595680e83c8bb2826fe"


async def main():
    phone = input("Phone number (e.g. +2348165330647): ").strip()

    client = TelegramClient(StringSession(), NEW_API_ID, NEW_API_HASH)
    await client.connect()
    print("Connected. Requesting code with the NEW api_id/hash...")

    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        print("PhoneNumberInvalidError - invalid number.")
        await client.disconnect()
        return
    except Exception as e:
        print(f"send_code_request raised: {type(e).__name__}: {e}")
        await client.disconnect()
        return

    print(f"type: {sent.type}  (class: {type(sent.type).__name__})")
    print(f"next_type: {sent.next_type}")

    code = input("Enter the OTP code (check the 'Telegram' chat on your logged-in device, or blank if nothing arrived): ").strip()
    if not code:
        print("No code entered - stopping. Nothing was added.")
        await client.disconnect()
        return

    try:
        await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        pw = input("2-step password: ").strip()
        try:
            await client.sign_in(password=pw)
        except Exception as e:
            print(f"Password sign-in failed: {type(e).__name__}: {e}")
            await client.disconnect()
            return
    except PhoneCodeInvalidError:
        print("PhoneCodeInvalidError - wrong/expired code.")
        await client.disconnect()
        return
    except Exception as e:
        print(f"sign_in raised: {type(e).__name__}: {e}")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"\nSUCCESS - logged in as: {me.first_name} (@{me.username}), id={me.id}")

    session_string = client.session.save()
    await client.disconnect()

    existing = await db.get_ad_account_by_phone(phone)
    if existing:
        await db.refresh_ad_account_session(existing["id"], session_string, status=existing["status"])
        account_id = existing["id"]
        print(f"Existing account (ID {account_id}) session refreshed.")
    else:
        account_id = await db.add_ad_account(phone, session_string, status="free")
        print(f"Added as new Ad Bot Account, ID: {account_id}")

    print("Joining it to all existing marketplaces in the background (uses the bot's normal OLD api_id from here on - that's fine, the session is already authenticated)...")
    asyncio.create_task(account_setup._join_new_account_to_all_marketplaces(account_id))
    await asyncio.sleep(5)  # give the join task a moment to actually start before the script exits
    print("Done. Check the bot / /accounts for status.")


if __name__ == "__main__":
    asyncio.run(main())
