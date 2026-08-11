"""
AutoAdly - Owner Ad Bot Account setup via phone + OTP (no manual session files)
"""

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneNumberInvalidError

import content_store as store
import database as db
import join_engine

router = Router()

API_ID = 37701222
API_HASH = "5e137a9ed23be5787dcdd9a92d9e48df"

ADD_PENDING = {}

@router.message(Command("addadbot"))
async def cmd_addadbot(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    ADD_PENDING[message.from_user.id] = {"step": "await_phone"}
    await message.reply("Send the phone number (with country code) for the new Ad Bot Account.\n\nExample: +15551234567")

@router.message(Command("canceladd"))
async def cmd_canceladd(message: Message):
    pending = ADD_PENDING.pop(message.from_user.id, None)
    if pending and pending.get("client"):
        try:
            await pending["client"].disconnect()
        except Exception:
            pass
    await message.reply("Cancelled.")

@router.message(F.text, ~F.text.startswith("/"), F.from_user.id.in_(ADD_PENDING.keys()))
async def on_addadbot_text(message: Message):
    user_id = message.from_user.id
    pending = ADD_PENDING.get(user_id)
    if not pending or not store.is_admin(user_id):
        return
    step = pending["step"]
    text = message.text.strip()

    if step == "await_phone":
        phone = text
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
        except PhoneNumberInvalidError:
            await message.reply("That phone number looks invalid. Please try again, or /canceladd to stop.")
            await client.disconnect()
            return
        except Exception as e:
            await message.reply(f"Could not send code: {e}")
            await client.disconnect()
            return
        pending.update({
            "step": "await_otp", "client": client, "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
        })
        ADD_PENDING[user_id] = pending
        await message.reply("Enter the OTP code sent to that number.")

    elif step == "await_otp":
        client = pending["client"]
        try:
            await client.sign_in(pending["phone"], text, phone_code_hash=pending["phone_code_hash"])
        except SessionPasswordNeededError:
            pending["step"] = "await_password"
            ADD_PENDING[user_id] = pending
            await message.reply("This account has Two-Step Verification enabled. Please send its password.")
            return
        except PhoneCodeInvalidError:
            await message.reply("That code is invalid. Please try again, or /canceladd to restart.")
            return
        except Exception as e:
            await message.reply(f"Sign-in failed: {e}")
            return
        await _finish_signin(message, user_id, client, pending["phone"])

    elif step == "await_password":
        client = pending["client"]
        try:
            await client.sign_in(password=text)
        except Exception as e:
            await message.reply(f"Password incorrect or sign-in failed: {e}")
            return
        pending["two_step_password"] = text
        await _finish_signin(message, user_id, client, pending["phone"], two_step_password=text)

async def _finish_signin(message, user_id, client, phone, two_step_password=None):
    session_string = client.session.save()
    await client.disconnect()
    ADD_PENDING.pop(user_id, None)

    existing = await db.get_ad_account_by_phone(phone)
    if existing:
        # Preserve whatever status it already had — do NOT force it back to "free",
        # since this may be an occupied account just getting its session refreshed
        # after a dead/expired login, not a brand new unassigned account.
        await db.refresh_ad_account_session(existing["id"], session_string, status=existing["status"])
        account_id = existing["id"]
        if two_step_password:
            await db.save_two_step_password(account_id, two_step_password)
        await message.reply(
            f"This number was already in the system (ID: {account_id}, status: {existing['status']}) — its session has been refreshed."
            + (" Two-step password saved." if two_step_password else "")
        )
        await message.reply("Re-joining it to all existing marketplaces in the background, in case it lost membership anywhere.")
        import asyncio
        asyncio.create_task(_join_new_account_to_all_marketplaces(account_id))
        return

    account_id = await db.add_ad_account(phone, session_string, status="free")
    if two_step_password:
        await db.save_two_step_password(account_id, two_step_password)

    import content_store as _store
    kind, uid, payload = _store.get_oldest_pending_fulfillment()

    if kind == "replacement":
        await db.mark_ad_account_status_no_fulfill(account_id, "occupied")
        import myadbot
        await myadbot.fulfill_replacement(uid, payload["index"], account_id, payload["ad_config"])
        _store.remove_pending_replacement(uid, payload["index"])
        await message.reply(f"Ad Bot Account added (ID: {account_id}) and immediately used to fulfill a queued replacement for user {uid}.")
    elif kind == "request":
        await db.mark_ad_account_status_no_fulfill(account_id, "occupied")
        import myadbot
        await myadbot._assign_account(uid, None, uid, account_id, send_new=True)
        _store.remove_pending_account_request(uid)
        remaining_empty = sum(1 for s in _store.get_customer_adbots(uid) if s.get("ad_account_id") is None)
        if remaining_empty > 0:
            _store.queue_pending_account_request(uid, created_at=payload)
        await message.reply(f"Ad Bot Account added (ID: {account_id}) and immediately assigned to a queued customer ({uid}).")
    else:
        await message.reply(
            f"Ad Bot Account added successfully!\n\n"
            f"ID: {account_id}\n"
            f"Phone: {phone}\n\n"
            f"It's now unassigned and ready to be given to a customer."
        )

    await message.reply("Joining it to all existing marketplaces in the background — this may take a while.")
    import asyncio
    asyncio.create_task(_join_new_account_to_all_marketplaces(account_id))

async def _join_new_account_to_all_marketplaces(account_id):
    try:
        await _do_join_new_account(account_id)
    except Exception as e:
        print(f"[account_setup] Auto-join for account {account_id} failed: {e}")

async def _do_join_new_account(account_id):
    folder_link = store.get_marketplace_folder_link()
    if folder_link:
        await join_engine.run_join_batch_for_specific_account(account_id, [folder_link])
        await _report_join_result(account_id)
        return
    all_usernames = await db.get_all_marketplace_usernames()
    if not all_usernames:
        return
    await join_engine.run_join_batch_for_specific_account(account_id, all_usernames)


@router.message(Command("accounts"))
async def cmd_accounts(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    accounts = await db.get_all_ad_accounts()
    if not accounts:
        await message.reply("No Ad Bot Accounts in the system yet.")
        return
    lines = ["<b>All Ad Bot Accounts</b>", ""]
    for a in accounts:
        pw_flag = " 🔑" if a["two_step_password"] else ""
        lines.append(f"ID {a['id']} — {a['phone']} — {a['status']}{pw_flag}")
    lines.append("")
    lines.append("Use /login (number) to retrieve a fresh login code and saved 2FA password for any account.")
    await message.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("login"))
async def cmd_login(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("Usage: /login +15551234567")
        return
    phone = parts[1].strip()
    account = await db.get_ad_account_by_phone(phone)
    if not account:
        await message.reply(f"No account found with phone {phone}.")
        return

    wait_msg = await message.reply(
        "Ready to catch the login code — go request one on your device/app now "
        "(e.g. tap 'Log in with phone number'). Checking for up to 60 seconds..."
    )

    import engine as _engine
    import asyncio as _asyncio
    import time as _time
    request_time = _time.time()

    # Deliberately does NOT call send_code_request itself — that would trigger
    # a brand-new competing login code and invalidate whatever code the
    # admin's own device is trying to log in with. Instead this just watches
    # the account's own existing session (already logged in) for a fresh
    # message from Telegram's official 777000 service account.
    code_text = "No new code arrived within 60 seconds — request one on your device, then try /login again."
    try:
        existing_client = await _engine.get_client(account["id"])
        for _attempt in range(30):
            await _asyncio.sleep(2)
            messages = await existing_client.get_messages(777000, limit=5)
            found = None
            for m in messages:
                if not m.text:
                    continue
                msg_time = m.date.timestamp() if m.date else 0
                if msg_time < request_time:
                    continue  # too old — from a previous request, ignore
                if "login code" in m.text.lower() or "code:" in m.text.lower():
                    found = m.text
                    break
            if found:
                code_text = found
                break
    except Exception as e:
        code_text = f"Could not check for the code: {e}"

    two_step = account["two_step_password"] or "(no 2-step password saved for this account)"

    reply = (
        f"<b>Login info for {phone}</b>\n\n"
        f"<b>Code message:</b>\n{code_text}\n\n"
        f"<b>Two-step password:</b> <code>{two_step}</code>"
    )
    await wait_msg.edit_text(reply, parse_mode="HTML")


async def _report_join_result(account_id):
    """Actually verifies membership count after a join attempt, marks the account
       as synced in the database if it genuinely succeeded (so a startup resume
       won't retry it needlessly), and tells the owner the real result."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    account = await db.get_ad_account_by_id(account_id)
    total_marketplaces = len(await db.get_all_marketplace_usernames())

    client = TelegramClient(StringSession(account["session_string"]), API_ID, API_HASH)
    await client.connect()
    joined_count = 0
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            joined_count += 1
    await client.disconnect()

    success = joined_count >= total_marketplaces * 0.8
    if success:
        await db.mark_marketplaces_synced(account_id, True)

    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if owner_id:
        import raw_api
        status = "OK" if success else "LOW — check the folder link or account status (will auto-retry on next bot restart)"
        await raw_api.send_message(
            owner_id,
            f"Join verification for account {account_id} ({account['phone']}): "
            f"joined {joined_count} chat(s) out of {total_marketplaces} known marketplaces. Status: {status}",
            [],
        )
    return success

async def resume_unsynced_joins():
    """Runs once shortly after bot startup. Finds any account whose marketplace
       join never got marked complete (e.g. it was killed mid-flight by a restart)
       and automatically resumes it."""
    import asyncio as _asyncio
    await _asyncio.sleep(15)
    try:
        unsynced = await db.get_unsynced_accounts()
        if not unsynced:
            return
        print(f"[account_setup] Resuming marketplace sync for {len(unsynced)} account(s) that never completed.")
        for account in unsynced:
            await _join_new_account_to_all_marketplaces(account["id"])
    except Exception as e:
        print(f"[account_setup] resume_unsynced_joins failed: {e}")
