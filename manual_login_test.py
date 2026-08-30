import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"


async def main():
    phone = input("Phone number (with country code, e.g. +2348165330647): ").strip()

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    print("Connected to Telegram.")

    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        print("PhoneNumberInvalidError - Telegram rejected this number outright.")
        await client.disconnect()
        return
    except Exception as e:
        print(f"send_code_request raised: {type(e).__name__}: {e}")
        await client.disconnect()
        return

    print("\n--- Raw SentCode response ---")
    print("type:", sent.type)
    print("type class:", type(sent.type).__name__)
    print("timeout:", sent.timeout)
    print("next_type:", sent.next_type)
    print("phone_code_hash:", sent.phone_code_hash)
    print("------------------------------\n")

    code = input("Enter the OTP code you actually received (leave blank + Enter if NOTHING arrived after waiting): ").strip()

    if not code:
        print("No code entered - stopping here. This confirms nothing arrived, independent of the bot entirely.")
        await client.disconnect()
        return

    try:
        await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        pw = input("This account has a 2-step password. Enter it: ").strip()
        try:
            await client.sign_in(password=pw)
        except Exception as e:
            print(f"Password sign-in failed: {type(e).__name__}: {e}")
            await client.disconnect()
            return
    except PhoneCodeInvalidError:
        print("PhoneCodeInvalidError - the code was wrong or expired.")
        await client.disconnect()
        return
    except Exception as e:
        print(f"sign_in raised: {type(e).__name__}: {e}")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"\nSUCCESS - logged in as: {me.first_name} (@{me.username}), id={me.id}")
    session_string = client.session.save()
    print(f"\nSession string (save this if you want to add it to the bot manually later):\n{session_string}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
