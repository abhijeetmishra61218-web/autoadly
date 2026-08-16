"""
AutoAdly - Detects when an Ad Bot Account gets restricted (UserBannedInChannelError
across multiple marketplaces), verifies via @SpamBot, notifies the owner with a
choice to notify the customer or not, and auto-replaces from stock if available.
"""

import asyncio
from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery

import raw_api
import content_store as store
import database as db
import config
import engine

router = Router()

# Tracks consecutive UserBannedInChannelError failures per ad_account_id.
# If an account fails on N consecutive DIFFERENT marketplaces, we treat it as
# genuinely restricted (not just one bad group) and start the replacement flow.
_ban_streak = {}
BAN_STREAK_THRESHOLD = 5
_already_flagged = set()

async def record_marketplace_ban(ad_account_id: int, marketplace_id: int):
    streak = _ban_streak.setdefault(ad_account_id, set())
    streak.add(marketplace_id)
    if len(streak) >= BAN_STREAK_THRESHOLD and ad_account_id not in _already_flagged:
        _already_flagged.add(ad_account_id)
        asyncio.create_task(handle_suspected_restriction(ad_account_id))

def record_marketplace_success(ad_account_id: int):
    _ban_streak.pop(ad_account_id, None)
    _already_flagged.discard(ad_account_id)

async def check_via_spambot(ad_account_id: int) -> str:
    """Messages @SpamBot from the account itself and returns its reply text."""
    client = await engine.get_client(ad_account_id)
    try:
        await client.send_message("SpamBot", "/start")
        await asyncio.sleep(3)
        messages = await client.get_messages("SpamBot", limit=1)
        if messages:
            return messages[0].text or "(no text in SpamBot reply)"
        return "(no reply received from SpamBot)"
    except Exception as e:
        return f"(could not reach SpamBot: {e})"

def _spambot_indicates_restriction(reply_text: str) -> bool:
    """SpamBot's standard clean message is very consistent — anything that doesn't
       match it is treated as an actual restriction."""
    if not reply_text:
        return False  # couldn't reach SpamBot at all — don't act on missing info
    lowered = reply_text.lower()
    clean_signals = ["no limits are currently applied", "free as a bird", "no limits"]
    return not any(signal in lowered for signal in clean_signals)

async def handle_suspected_restriction(ad_account_id: int):
    account = await db.get_ad_account_by_id(ad_account_id)
    spambot_reply = await check_via_spambot(ad_account_id)

    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if not owner_id:
        return

    if not _spambot_indicates_restriction(spambot_reply):
        # False alarm — account is genuinely clean. Clear the ban streak and just inform the owner, no replacement.
        record_marketplace_success(ad_account_id)
        try:
            await raw_api.send_message(
                owner_id,
                f"Checked Account ID {ad_account_id} ({account['phone']}) via @SpamBot after repeated post failures — it's actually clean:\n\n{spambot_reply}\n\nNo replacement needed. The recent failures were likely a per-group issue (e.g. a specific group's restriction), not an account-wide ban.",
                [],
            )
        except Exception as e:
            print(f"[restriction_monitor] could not notify owner of false alarm: {e}")
        return

    # Find which customer/slot owns this account, so we can offer to notify them right away
    all_adbots = store.load_customer_adbots()
    target_uid, target_idx, target_name = None, None, None
    for uid_str, bots in all_adbots.items():
        for i, bot in enumerate(bots):
            if bot["ad_account_id"] == ad_account_id:
                target_uid, target_idx, target_name = int(uid_str), i, bot["name"]
                break

    text = (
        f"⚠️ Ad Bot Account restriction suspected!\n\n"
        f"Account ID: {ad_account_id}\n"
        f"Phone: {account['phone']}\n\n"
        f"@SpamBot says:\n{spambot_reply}\n\n"
        f"We are replacing it now if a free account is available."
    )
    rows = []
    if target_uid is not None:
        rows = [[
            {"text": "Notify Customer Now", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:yes"},
            {"text": "Don't Notify", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:no"},
        ]]
    try:
        await raw_api.send_message(owner_id, text, rows)
    except Exception as e:
        print(f"[restriction_monitor] could not notify owner: {e}")

    await do_replacement(ad_account_id, owner_id, target_uid, target_idx, target_name)

@router.callback_query(F.data.startswith("restrictdetected:"))
async def cb_restrict_detected_notify(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    _, uid_str, idx_str, choice = callback.data.split(":")
    target_uid = int(uid_str)
    if choice == "yes":
        adbots = store.get_customer_adbots(target_uid)
        idx = int(idx_str)
        name = adbots[idx]["name"] if idx < len(adbots) else "your Ad Bot Account"
        try:
            bot = Bot(token=config.BOT_TOKEN)
            await bot.send_message(target_uid, f"Your Ad Bot Account <b>{name}</b> hit a Telegram restriction. We're replacing it now — you'll be notified again once it's done.", parse_mode="HTML")
            await bot.session.close()
        except Exception:
            pass
        await callback.message.edit_text("Customer notified that replacement is in progress.")
    else:
        await callback.message.edit_text("Customer was not notified yet.")
    await callback.answer()

async def do_replacement(old_account_id: int, owner_id: int, target_uid=None, target_idx=None, target_name=None):
    if target_uid is None:
        # Find which customer/slot owns this account (fallback if called directly, not via handle_suspected_restriction)
        all_adbots = store.load_customer_adbots()
        for uid_str, bots in all_adbots.items():
            for i, bot in enumerate(bots):
                if bot["ad_account_id"] == old_account_id:
                    target_uid, target_idx, target_name = int(uid_str), i, bot["name"]
                    break
    if target_uid is None:
        return  # unassigned account, nothing to replace for

    existing_ad = await db.get_active_ad_for_account(old_account_id)
    ad_config = None
    if existing_ad:
        ad_config = {
            "source_chat_id": existing_ad["source_chat_id"],
            "source_message_id": existing_ad["source_message_id"],
            "category": existing_ad["category"],
            "marketplace_list_id": existing_ad["marketplace_list_id"],
            "source_username": existing_ad["source_username"],
        }
        await db.stop_advertisement(existing_ad["id"])

    # Capture old profile (name/bio/photo) to copy onto the replacement, except username
    old_profile = {"name": target_name, "bio": None, "photo_bytes": None}
    try:
        import io
        old_client = await engine.get_client(old_account_id)
        me = await old_client.get_me()
        old_profile["bio"] = getattr(me, "about", None)
        photo_buf = io.BytesIO()
        downloaded = await old_client.download_profile_photo(me, file=photo_buf)
        if downloaded:
            photo_buf.seek(0)
            old_profile["photo_bytes"] = photo_buf
    except Exception as e:
        print(f"[restriction_monitor] could not capture old profile: {e}")

    await db.mark_ad_account_status_no_fulfill(old_account_id, "restricted")

    new_account = await db.get_free_ad_account()
    if not new_account:
        store.queue_pending_replacement(target_uid, target_idx, ad_config)
        # note: old_profile (with live photo bytes) can't be serialized to the JSON queue,
        # so a queued replacement falls back to a fresh random profile rather than a copy.
        # This only affects the (uncommon) case where no account was free at the moment of detection.
        rows = [[
            {"text": "Notify Customer", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:yes"},
            {"text": "Already Notified", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:no"},
        ]]
        try:
            await raw_api.send_message(owner_id, f"No free accounts available right now — replacement for user {target_uid} is queued and will happen automatically.", rows)
        except Exception:
            pass
        return

    import myadbot
    await myadbot.fulfill_replacement(target_uid, target_idx, new_account["id"], ad_config, old_profile=old_profile)

    try:
        rows = [[{"text": "Notify Customer", "callback_data": f"restrictnotify:{target_uid}:{target_idx}:yes"},
                 {"text": "Don't Notify", "callback_data": f"restrictnotify:{target_uid}:{target_idx}:no"}]]
        await raw_api.send_message(
            owner_id,
            f"Replacement complete for user {target_uid} ({target_name}). New account: {new_account['phone']}.\n\nNotify the customer?",
            rows,
        )
    except Exception as e:
        print(f"[restriction_monitor] could not send owner confirmation: {e}")

@router.callback_query(F.data.startswith("restrictnotify:"))
async def cb_restrict_notify(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    _, uid_str, idx_str, choice = callback.data.split(":")
    target_uid = int(uid_str)

    if choice == "yes":
        adbots = store.get_customer_adbots(target_uid)
        idx = int(idx_str)
        name = adbots[idx]["name"] if idx < len(adbots) else "your Ad Bot Account"
        try:
            bot = Bot(token=config.BOT_TOKEN)
            await bot.send_message(target_uid, f"Your Ad Bot Account <b>{name}</b> was replaced due to a Telegram restriction. It's back up and running normally.", parse_mode="HTML")
            await bot.session.close()
        except Exception:
            pass
        await callback.message.edit_text("Customer notified.")
    else:
        await callback.message.edit_text("Customer was not notified.")
    await callback.answer()

DAILY_RECHECK_INTERVAL_SECONDS = 24 * 60 * 60

async def daily_recheck_restricted_accounts():
    """Runs once daily: re-tests every restricted/banned account via @SpamBot.
       Any that come back clean are returned to the free pool (auto-fulfilling
       whoever's next in the queue) and the owner is notified."""
    admins = store.load_admins()
    owner_id = admins.get("owner_id")

    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT id, phone, status FROM ad_accounts WHERE status IN ('restricted', 'banned')")
        rows = await cursor.fetchall()

    if not rows:
        return

    recovered = []
    for r in rows:
        try:
            spambot_reply = await check_via_spambot(r["id"])
        except Exception as e:
            print(f"[restriction_monitor] daily recheck failed for account {r['id']}: {e}")
            continue
        if not _spambot_indicates_restriction(spambot_reply):
            await db.mark_ad_account_status(r["id"], "free")
            recovered.append((r["id"], r["phone"]))

    if recovered and owner_id:
        lines = [f"Daily restriction recheck: {len(recovered)} account(s) came back clean and were returned to the free pool:"]
        for acc_id, phone in recovered:
            lines.append(f"  ID {acc_id} — {phone}")
        try:
            await raw_api.send_message(owner_id, "\n".join(lines), [])
        except Exception as e:
            print(f"[restriction_monitor] could not notify owner of recovered accounts: {e}")

async def daily_recheck_loop():
    while True:
        try:
            await daily_recheck_restricted_accounts()
        except Exception as e:
            print(f"[restriction_monitor] daily recheck loop failed: {e}")
        await asyncio.sleep(DAILY_RECHECK_INTERVAL_SECONDS)
