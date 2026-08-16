"""
AutoAdly - Owner admin commands: /users, /premium, /activate, /ban, /unban, /dmall, /dm
"""

import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram import Bot

import content_store as store
import config
import raw_api
import database as db

router = Router()

def _find_plan(name_or_id):
    plans = store.load_plans()
    name_or_id_lower = name_or_id.lower()
    for p in plans:
        if p["id"].lower() == name_or_id_lower or p["name"].lower() == name_or_id_lower:
            return p
    return None

@router.message(Command("users"))
async def cmd_users(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    users = store.load_all_users()
    if not users:
        await message.reply("No registered users yet.")
        return
    lines = [f"<b>Registered Users</b> ({len(users)})", ""]
    for uid, info in users.items():
        username = info.get("username") or "no username"
        lines.append(f"@{username} — <code>{uid}</code>")
    text = "\n".join(lines)
    if len(text) > 3500:
        text = text[:3500] + "\n\n...(truncated, too many users to show in one message)"
    await message.reply(text, parse_mode="HTML")

@router.message(Command("premium"))
async def cmd_premium(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    subs = store.load_subscriptions()
    users = store.load_all_users()
    if not subs:
        await message.reply("No active subscriptions yet.")
        return
    lines = [f"<b>Premium Users</b> ({len(subs)})", ""]
    now = time.time()
    for uid, sub in subs.items():
        username = users.get(uid, {}).get("username") or "no username"
        plan = store.get_plan(sub["plan_id"])
        plan_name = plan["name"] if plan else sub["plan_id"]
        expiry_str = time.strftime("%Y-%m-%d", time.localtime(sub["expiry"]))
        status = "active" if sub["expiry"] > now else "expired"
        lines.append(f"@{username} — {plan_name} — expires {expiry_str} ({status})")
    text = "\n".join(lines)
    if len(text) > 3500:
        text = text[:3500] + "\n\n...(truncated)"
    await message.reply(text, parse_mode="HTML")

@router.message(Command("activate"))
async def cmd_activate(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 4 or not parts[1].startswith("@"):
        await message.reply("Usage: /activate @username PLAN DAYS\n\nExample: /activate @john Starter 1")
        return
    _, username_raw, plan_raw, days_raw = parts
    username = username_raw.lstrip("@")

    if not days_raw.isdigit():
        await message.reply("DAYS must be a whole number.")
        return
    days = int(days_raw)

    plan = _find_plan(plan_raw)
    if not plan:
        available = ", ".join(p["name"] for p in store.load_plans())
        await message.reply(f"Plan '{plan_raw}' not found. Available plans: {available}")
        return

    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet. Ask them to send /start first, then try again.")
        return

    sub = store.activate_subscription(target_uid, plan["id"], days=days)
    expiry_str = time.strftime("%Y-%m-%d", time.localtime(sub["expiry"]))
    await message.reply(f"Activated {plan['name']} for @{username} — expires {expiry_str}.")

    try:
        bot = Bot(token=config.BOT_TOKEN)
        await bot.send_message(target_uid, f"Your {plan['name']} plan has been activated by the owner.\n\nExpires: {expiry_str}\n\nSend /start and open My Ad Bot to get set up.")
        await bot.session.close()
    except Exception as e:
        await message.reply(f"(Note: could not notify the user directly — {e})")

    try:
        import myadbot
        quota = plan.get("max_ad_accounts", 1)
        await myadbot.request_accounts_for_customer(target_uid, target_uid, quota)
    except Exception as e:
        await message.reply(f"(Note: auto-assignment of Ad Bot Accounts failed — {e})")

@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /ban @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet — nothing to ban.")
        return
    store.ban_user(target_uid)
    await message.reply(f"@{username} has been banned.")

@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /unban @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return
    store.unban_user(target_uid)
    await message.reply(f"@{username} has been unbanned.")

@router.message(Command("dm"))
async def cmd_dm(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3 or not parts[1].startswith("@"):
        await message.reply("Usage: /dm @username your message here")
        return
    username = parts[1].lstrip("@")
    text = parts[2]
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return
    try:
        bot = Bot(token=config.BOT_TOKEN)
        await bot.send_message(target_uid, text)
        await bot.session.close()
        await message.reply(f"Message sent to @{username}.")
    except Exception as e:
        await message.reply(f"Could not send message: {e}")

@router.message(Command("dmall"))
async def cmd_dmall(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.reply("Usage: /dmall your message here")
        return
    text = parts[1]
    users = store.load_all_users()
    if not users:
        await message.reply("No registered users to broadcast to.")
        return

    await message.reply(f"Broadcasting to {len(users)} user(s), this may take a moment...")

    bot = Bot(token=config.BOT_TOKEN)
    sent = 0
    failed = 0
    for uid in users.keys():
        try:
            await bot.send_message(int(uid), text)
            sent += 1
        except Exception:
            failed += 1
    await bot.session.close()
    await message.reply(f"Broadcast complete. Sent: {sent}, Failed: {failed}.")


@router.message(Command("change"))
async def cmd_change(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /change @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return
    adbots = store.get_customer_adbots(target_uid)
    if not adbots:
        await message.reply(f"@{username} has no Ad Bot Accounts.")
        return

    if len(adbots) == 1:
        await _do_change(message, target_uid, 0)
        return

    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"admchange:{target_uid}:{i}"}] for i, bot in enumerate(adbots)]
    await raw_api.send_message(message.chat.id, f"Which of @{username}'s accounts was banned?", rows)

@router.callback_query(F.data.startswith("admchange:"))
async def cb_change_pick(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    _, uid_str, idx_str = callback.data.split(":")
    await _do_change(callback.message, int(uid_str), int(idx_str))
    await callback.answer()

async def _do_change(message_or_callback_msg, target_uid, idx):
    adbots = store.get_customer_adbots(target_uid)
    if idx >= len(adbots):
        await message_or_callback_msg.reply("Account not found.")
        return
    bot = adbots[idx]
    old_account_id = bot["ad_account_id"]

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

    await db.mark_ad_account_status_no_fulfill(old_account_id, "banned")

    new_account = await db.get_free_ad_account()
    if new_account:
        import myadbot
        await myadbot.fulfill_replacement(target_uid, idx, new_account["id"], ad_config, reason="banned")
        await message_or_callback_msg.reply("Replaced instantly with a free account. Customer notified.")
    else:
        store.queue_pending_replacement(target_uid, idx, ad_config)
        await message_or_callback_msg.reply("No free accounts right now — queued. It will be assigned automatically and the customer notified the moment /addadbot adds one.")


@router.message(Command("priority"))
async def cmd_priority(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /priority @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return

    sub = store.get_subscription(target_uid)
    if not sub:
        await message.reply(f"@{username} has no active subscription.")
        return
    plan = store.get_plan(sub["plan_id"])
    quota = plan.get("max_ad_accounts", 1) if plan else 1
    store.ensure_customer_slots(target_uid, quota)
    current_filled = sum(1 for s in store.get_customer_adbots(target_uid) if s.get("ad_account_id"))
    needed = max(0, quota - current_filled)

    if needed == 0:
        await message.reply(f"@{username} already has their full quota ({current_filled}/{quota}).")
        return

    import myadbot
    assigned = 0
    for _ in range(needed):
        account = await db.get_free_ad_account()
        if not account:
            break
        await myadbot._assign_account(target_uid, None, target_uid, account["id"], send_new=True)
        assigned += 1

    still_needed = needed - assigned
    if still_needed > 0:
        # created_at=0 forces this customer to the very front of the queue,
        # ahead of everyone else waiting — queue_pending_account_request()
        # normally PRESERVES an existing timestamp when re-queuing, which is
        # why /priority previously said "prioritized" but didn't actually
        # change anyone's position.
        for _ in range(still_needed):
            store.queue_pending_account_request(target_uid, created_at=0)
        await message.reply(f"Assigned {assigned} account(s) instantly to @{username}. Prioritized in queue for the remaining {still_needed} — they'll be first in line for the next account(s) added.")
    else:
        await message.reply(f"Assigned all {assigned} needed account(s) to @{username} instantly.")


@router.message(Command("view"))
async def cmd_view(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /view @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return

    sub = store.get_subscription(target_uid)
    plan = store.get_plan(sub["plan_id"]) if sub else None
    quota = plan.get("max_ad_accounts", 1) if plan else 0
    adbots = store.get_customer_adbots(target_uid)

    running = 0
    stopped = 0
    for bot in adbots:
        ad = await db.get_active_ad_for_account(bot["ad_account_id"])
        if ad:
            running += 1
        else:
            stopped += 1

    fulfilled = len(adbots)
    unfulfilled = max(0, quota - fulfilled)
    has_pending_new_request = store.get_pending_account_request(target_uid) is not None

    lines = [
        f"<b>Ad Bot Accounts for @{username}</b>",
        "",
        f"Plan: {plan['name'] if plan else 'None'}",
        f"Quota: {quota}",
        f"Fulfilled: {fulfilled}",
        f"Unfulfilled (queued): {unfulfilled}",
        f"Running: {running}",
        f"Stopped: {stopped}",
        f"Waiting on a new account request: {'Yes' if has_pending_new_request else 'No'}",
        "",
    ]
    for i, bot in enumerate(adbots):
        if bot.get("ad_account_id"):
            ad = await db.get_active_ad_for_account(bot["ad_account_id"])
            status = "Running" if ad else "Stopped"
            account = await db.get_ad_account_by_id(bot["ad_account_id"])
            phone = store.normalize_phone(account["phone"]) if account else "unknown"
            lines.append(f"{store.slot_display_name(bot, i)} — {status} — {phone}")
        else:
            lines.append(f"{store.slot_display_name(bot, i)} — Unassigned")

    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("sweetspot"))
async def cmd_sweetspot(message: Message):
    """Shows what the staggered low-quality sweet-spot scheduler is doing
       right now: which marketplaces are still testing (and at what slot/
       interval/streak) and which have graduated to a fixed interval."""
    import logging
    debug_logger = logging.getLogger("cmd_sweetspot")
    debug_logger.info(f"/sweetspot received from user_id={message.from_user.id}")

    if not store.is_admin(message.from_user.id):
        debug_logger.info(f"/sweetspot: user_id={message.from_user.id} failed is_admin check — ignoring")
        return

    try:
        import low_quality_stagger as lqs

        states = await db.get_all_sweet_spot_states()
        debug_logger.info(f"/sweetspot: is_admin passed, {len(states)} state row(s) found")
        if not states:
            await message.reply("No low-quality marketplaces are being tracked by the sweet-spot scheduler right now.")
            return

        by_ad = {}
        for s in states:
            by_ad.setdefault(s["ad_id"], []).append(s)

        now = time.time()
        lines = ["<b>Low-quality sweet-spot scheduler</b>", ""]
        for ad_id, rows in by_ad.items():
            lines.append(f"<b>Ad #{ad_id}</b>")
            for s in rows:
                interval_min = s["interval_seconds"] // 60
                username = s["chat_username"]
                label = f"@{username}" if username and not str(username).lstrip("-").isdigit() else str(username)
                if s["state"] == "graduated":
                    lines.append(f"  ✅ {label} — graduated — fixed {interval_min}min interval")
                else:
                    eta = max(0, int(s["next_run_at"] - now))
                    lines.append(
                        f"  ⏳ {label} — testing, slot {s['slot_index']} ({interval_min}min) — "
                        f"streak {s['streak']}/{lqs.GRADUATION_STREAK} — next attempt in {eta // 60}m{eta % 60}s"
                    )
            lines.append("")

        await message.reply("\n".join(lines).strip(), parse_mode="HTML")
        debug_logger.info("/sweetspot: reply sent successfully")
    except Exception:
        debug_logger.exception("/sweetspot: unhandled exception while building/sending reply")
        try:
            await message.reply(f"/sweetspot hit an internal error — check crash_log.txt for the traceback.")
        except Exception:
            debug_logger.exception("/sweetspot: even the fallback error reply failed to send")


@router.message(Command("cancel"))
async def cmd_cancel_priority(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /cancel @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return
    store.remove_pending_account_request(target_uid)
    await message.reply(f"Removed @{username} from the account request queue.")

@router.message(Command("queue"))
async def cmd_queue(message: Message):
    """Admin/owner-only: lists every customer waiting for an Ad Bot Account,
       priority customers first, then everyone else in fair (first-come) order."""
    if not store.is_admin(message.from_user.id):
        return
    entries = store.list_pending_account_requests_sorted()
    if not entries:
        await message.reply("The queue is empty — nobody is waiting for an Ad Bot Account.")
        return

    lines = ["<b>Account Request Queue</b>", ""]
    for pos, (uid, created_at, is_priority) in enumerate(entries, start=1):
        username = store.get_username_by_uid(uid)
        label = f"@{username}" if username else f"user_id={uid}"
        tag = "⭐ priority" if is_priority else "normal"
        waited = time.strftime("%Y-%m-%d %H:%M", time.localtime(created_at)) if created_at else "unknown"
        lines.append(f"{pos}. {label} — {tag} (queued: {waited})")
    await message.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("rpriority"))
async def cmd_remove_priority(message: Message):
    """Admin/owner-only: removes a customer from priority status, dropping
       them back to their fair position in the queue instead of the very front."""
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /rpriority @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return

    entry = store.get_pending_account_request(target_uid)
    if entry is None:
        await message.reply(f"@{username} isn't in the account request queue.")
        return
    if not store.is_priority_request(entry):
        await message.reply(f"@{username} is already non-priority.")
        return

    store.remove_priority(target_uid)
    await message.reply(f"@{username} removed from priority — back in the queue at their fair position.")

@router.message(Command("expire"))
async def cmd_expire_user(message: Message):
    """Admin-only: immediately expires a customer's plan — stops their ads,
       frees their Ad Bot Accounts back to the pool (auto-fulfilling the next
       queued customer, same as natural expiry), and removes them from the
       account-request/replacement queues."""
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /expire @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return

    sub = store.get_subscription(target_uid)
    if not sub:
        await message.reply(f"@{username} has no active subscription to expire.")
        return

    plan = store.get_plan(sub.get("plan_id"))
    plan_name = plan["name"] if plan else sub.get("plan_id")

    import subscription_expiry
    # release_customer_accounts() also removes target_uid from the
    # new-account-request and replacement queues, so it doesn't need
    # repeating here.
    freed, restricted = await subscription_expiry.release_customer_accounts(target_uid, plan_name, source="ended by admin")

    store.mark_subscription_flag(target_uid, "reclaimed", True)
    store.mark_subscription_flag(target_uid, "expiry", time.time())

    try:
        await raw_api.send_message(
            target_uid,
            f"Your <b>{plan_name}</b> subscription has been ended by the admin. "
            f"Your advertisements have been stopped and your Ad Bot Accounts have been released.\n\n"
            f"Tap Buy Ad Bot to renew and get set up again.",
            [],
        )
    except Exception as e:
        print(f"[cmd_expire_user] could not notify user {target_uid}: {e}")

    await message.reply(
        f"@{username}'s {plan_name} plan has been expired. "
        f"{freed} account(s) freed back to the pool, {restricted} held back as restricted, "
        f"and they've been removed from any pending queues."
    )

@router.message(Command("reconcile"))
async def cmd_reconcile_queue(message: Message):
    """Admin-only: scans every customer for accounts they're still owed
       (filled < plan quota) but who fell out of both the replacement and
       new-account-request queues, and re-queues them fairly by purchase date."""
    if not store.is_admin(message.from_user.id):
        return
    fixed = store.reconcile_account_request_queue()
    if not fixed:
        await message.reply("Checked — everyone owed accounts is already correctly queued. Nothing to fix.")
        return
    lines = ["Found and fixed the following customer(s) missing from the queue:"]
    for uid, missing in fixed:
        lines.append(f"  user_id={uid} — {missing} account(s) restored to queue")
    await message.reply("\n".join(lines))

@router.message(Command("remove"))
async def cmd_remove_marketplace(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("Usage: /remove <username or link>\n\nExample: /remove @somegroup or /remove https://t.me/somegroup")
        return

    raw = parts[1].strip()
    username = raw.split("t.me/")[-1].lstrip("@").strip("/")

    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM marketplaces WHERE chat_username = ?", (username,))
        marketplace = await cursor.fetchone()

    if not marketplace:
        await message.reply(f"No marketplace found matching '{username}' in the system.")
        return

    wait_msg = await message.reply(f"Removing {username} — leaving it on all ad accounts and cleaning up, please wait...")

    import engine
    import join_engine

    master_id = store.get_master_account_id()
    removed_from_master = False
    if master_id:
        try:
            master_client = await engine.get_client(master_id)
            entity = await master_client.get_entity(marketplace["chat_id"])
            removed_from_master = await join_engine.remove_entity_from_master_folder(entity)
            try:
                await master_client.delete_dialog(entity)
            except Exception:
                pass
        except Exception as e:
            print(f"[cmd_remove] master cleanup failed: {e}")

    accounts = await db.get_all_ad_accounts()
    left_count = 0
    for account in accounts:
        if account["id"] == master_id:
            continue
        try:
            client = await engine.get_client(account["id"])
            entity = await client.get_entity(marketplace["chat_id"])
            await client.delete_dialog(entity)
            left_count += 1
        except Exception:
            pass

    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM marketplace_list_items WHERE marketplace_id = ?", (marketplace["id"],))
        await conn.execute("DELETE FROM forum_topics WHERE marketplace_id = ?", (marketplace["id"],))
        await conn.execute("DELETE FROM marketplaces WHERE id = ?", (marketplace["id"],))
        await conn.commit()

    await wait_msg.edit_text(
        f"Removed {username}:\n"
        f"- Left on {left_count} ad account(s)\n"
        f"- {'Removed from' if removed_from_master else 'Could not remove from'} master folder (future joins won't include it)\n"
        f"- Deleted from the marketplace database"
    )

@router.message(Command("freeacc"))
async def cmd_free_accounts(message: Message):
    """Owner-only: lists every Ad Bot Account that is free (not occupied, not restricted/banned)."""
    if not store.is_admin(message.from_user.id):
        return
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT id, phone FROM ad_accounts WHERE status = 'free' ORDER BY id")
        rows = await cursor.fetchall()
    if not rows:
        await message.reply("No free Ad Bot Accounts right now.")
        return
    lines = [f"<b>Free Ad Bot Accounts ({len(rows)})</b>", ""]
    for r in rows:
        lines.append(f"ID {r['id']} — {r['phone']}")
    await message.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("occacc"))
async def cmd_occupied_accounts(message: Message):
    """Owner-only: lists every Ad Bot Account currently assigned to a customer, with owner + slot name."""
    if not store.is_admin(message.from_user.id):
        return
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT id, phone FROM ad_accounts WHERE status = 'occupied' ORDER BY id")
        rows = await cursor.fetchall()
    if not rows:
        await message.reply("No occupied Ad Bot Accounts right now.")
        return

    owner_by_account = {}
    all_adbots = store.load_customer_adbots()
    for uid_str, bots in all_adbots.items():
        for i, bot in enumerate(bots):
            if bot.get("ad_account_id") is not None:
                owner_by_account[bot["ad_account_id"]] = (uid_str, store.slot_display_name(bot, i))

    lines = [f"<b>Occupied Ad Bot Accounts ({len(rows)})</b>", ""]
    for r in rows:
        owner = owner_by_account.get(r["id"])
        if owner:
            uid_str, slot_name = owner
            username = store.get_username_by_uid(uid_str)
            owner_label = f"@{username}" if username else f"user_id={uid_str}"
            lines.append(f"ID {r['id']} — {r['phone']} — {owner_label} ({slot_name})")
        else:
            lines.append(f"ID {r['id']} — {r['phone']} — (owner not found)")
    await message.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("restricted"))
async def cmd_restricted_accounts(message: Message):
    """Owner-only: lists every Ad Bot Account marked restricted or banned.
       These are automatically rechecked daily via @SpamBot (see restriction_monitor.daily_recheck_loop)
       and freed up automatically the moment they come back clean."""
    if not store.is_admin(message.from_user.id):
        return
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT id, phone, status FROM ad_accounts WHERE status IN ('restricted', 'banned') ORDER BY id")
        rows = await cursor.fetchall()
    if not rows:
        await message.reply("No restricted/banned Ad Bot Accounts right now.")
        return
    lines = [f"<b>Restricted/Banned Ad Bot Accounts ({len(rows)})</b>", ""]
    for r in rows:
        lines.append(f"ID {r['id']} — {r['phone']} — {r['status']}")
    lines.append("")
    lines.append("These are automatically rechecked daily via @SpamBot and freed up if clean again.")
    await message.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("removeno"))
async def cmd_remove_account_number(message: Message):
    """Owner-only: permanently deletes an Ad Bot Account from the system by ID.
       To use that phone number again later, it must be logged in fresh via /login."""
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("Usage: /removeno (account ID number)\n\nExample: /removeno 12")
        return
    account_id = int(parts[1])

    account = await db.get_ad_account_by_id(account_id)
    if not account:
        await message.reply(f"No Ad Bot Account found with ID {account_id}.")
        return

    # If assigned to a customer right now, stop its ad and clear it from
    # their slot — preserving name/bio/photo, same as the expiry flow, so
    # the slot looks the same if a different account fills it later.
    all_adbots = store.load_customer_adbots()
    changed = False
    for uid_str, bots in all_adbots.items():
        for bot in bots:
            if bot.get("ad_account_id") == account_id:
                existing_ad = await db.get_active_ad_for_account(account_id)
                if existing_ad:
                    await db.stop_advertisement(existing_ad["id"])
                bot["ad_account_id"] = None
                changed = True
    if changed:
        store.save_customer_adbots(all_adbots)

    import engine
    await engine.disconnect_and_forget_client(account_id)
    await db.delete_ad_account(account_id)

    await message.reply(
        f"Ad Bot Account ID {account_id} ({account['phone']}) has been permanently removed from the system.\n\n"
        f"To use this number again, it needs to be logged in fresh via /login — nothing was preserved."
    )

@router.message(Command("checkall"))
async def cmd_check_all(message: Message):
    """Owner-only: manually triggers an immediate full concurrent @SpamBot sweep
       of every occupied account (same checks as the automatic 6-hourly sweep),
       instead of waiting for the schedule. Anything flagged gets a Replace/Ignore
       prompt here as usual — this just kicks the check off early."""
    if not store.is_admin(message.from_user.id):
        return
    accounts = await db.get_occupied_ad_accounts()
    if not accounts:
        await message.reply("No occupied Ad Bot Accounts to check.")
        return
    await message.reply(
        f"Checking {len(accounts)} occupied Ad Bot Account(s) via @SpamBot at the same time — "
        f"you'll get a message here for anything flagged as restricted."
    )
    import asyncio
    import restriction_monitor as rm
    asyncio.create_task(rm.full_sweep_all_accounts())

@router.message(Command("temp1"))
async def cmd_temp1_preview(message: Message):
    """Owner-only, preview only: shows exactly what a customer would receive if
       one of their Ad Bot Accounts were replaced right now. Does NOT touch any
       account, status, subscription, or queue — purely a preview."""
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /temp1 @username")
        return
    username = parts[1].lstrip("@")
    target_uid = store.get_uid_by_username(username)
    if not target_uid:
        await message.reply(f"@{username} hasn't started the bot yet.")
        return
    adbots = store.get_customer_adbots(target_uid)
    if not adbots:
        await message.reply(f"@{username} has no Ad Bot Accounts.")
        return

    if len(adbots) == 1:
        await _send_temp1_preview(message, adbots[0], 0)
        return

    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"temp1pick:{target_uid}:{i}"}] for i, bot in enumerate(adbots)]
    await raw_api.send_message(message.chat.id, f"Preview a replacement for which of @{username}'s accounts?", rows)

@router.callback_query(F.data.startswith("temp1pick:"))
async def cb_temp1_pick(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    _, uid_str, idx_str = callback.data.split(":")
    target_uid, idx = int(uid_str), int(idx_str)
    adbots = store.get_customer_adbots(target_uid)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    await _send_temp1_preview(callback.message, adbots[idx], idx)
    await callback.answer()

async def _send_temp1_preview(message_or_callback_msg, slot, idx):
    import myadbot
    display_name = store.slot_display_name(slot, idx)
    lines = [f"<b>Preview for {display_name}</b> — exactly what the customer would receive:", ""]
    for reason in ("restricted", "banned"):
        for has_ad in (True, False):
            label = f"if {reason}, {'ad running' if has_ad else 'no ad set yet'}"
            text = myadbot.build_replacement_notice_text(display_name, reason, has_ad_config=has_ad)
            lines.append(f"<b>{label}:</b>\n{text}\n")
    await message_or_callback_msg.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("free"))
async def cmd_free_number(message: Message):
    """Owner-only: pulls a phone number off whichever customer currently has it
       (preserving their slot's name/bio/photo, same as /removeno), SpamBot-checks
       it, and — if clean — returns it to the free pool via the normal
       mark_ad_account_status('free') path, so it gets auto-assigned to whoever's
       next in the queue exactly like any other freed account. If it comes back
       restricted, it's held back instead of being handed to the next customer."""
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("Usage: /free +15551234567")
        return
    phone = store.normalize_phone(parts[1])
    account = await db.get_ad_account_by_phone(phone)
    if not account:
        await message.reply(f"No Ad Bot Account found with phone {phone}.")
        return
    account_id = account["id"]

    all_adbots = store.load_customer_adbots()
    owner_uid, owner_idx = None, None
    for uid_str, bots in all_adbots.items():
        for i, bot in enumerate(bots):
            if bot.get("ad_account_id") == account_id:
                owner_uid, owner_idx = int(uid_str), i
                break

    if owner_uid is not None:
        existing_ad = await db.get_active_ad_for_account(account_id)
        if existing_ad:
            await db.stop_advertisement(existing_ad["id"])
        all_adbots[str(owner_uid)][owner_idx]["ad_account_id"] = None
        store.save_customer_adbots(all_adbots)

    await message.reply(f"Checking account {account_id} ({phone}) via @SpamBot before freeing it...")
    import restriction_monitor as rm
    spambot_reply = await rm.check_via_spambot(account_id)

    if rm._spambot_indicates_restriction(spambot_reply):
        await db.mark_ad_account_status_no_fulfill(account_id, "restricted")
        await message.reply(
            f"Account {account_id} ({phone}) came back RESTRICTED on @SpamBot check — "
            f"held back, NOT returned to the free pool.\n\n{spambot_reply}"
        )
        return

    await db.mark_ad_account_status(account_id, "free")
    await message.reply(
        f"Account {account_id} ({phone}) is clean and has been returned to the free pool — "
        f"it will show in /freeacc and auto-assign to whoever's next in the queue, same as any other freed account."
    )

# ---- /oc — owner command reference ----
# Add a (command, usage, description) tuple here whenever a new owner-only
# command is added anywhere in the codebase, so /oc always stays accurate.
OWNER_COMMANDS = [
    ("/users", "/users", "List every registered user and their Telegram ID."),
    ("/premium", "/premium", "List every customer with an active subscription."),
    ("/activate", "/activate @username PLAN DAYS", "Manually activate/renew a customer's subscription."),
    ("/ban", "/ban @username", "Ban a user from using the bot."),
    ("/unban", "/unban @username", "Unban a previously banned user."),
    ("/dm", "/dm @username your message", "Send a direct message to one customer."),
    ("/dmall", "/dmall your message", "Broadcast a message to every registered user."),
    ("/change", "/change @username", "Mark one of a customer's accounts as banned and replace it."),
    ("/priority", "/priority @username", "Prioritize a customer's remaining account requests."),
    ("/view", "/view @username", "View a customer's full account/subscription details."),
    ("/cancel", "/cancel @username", "Remove a customer from the new-account-request queue."),
    ("/expire", "/expire @username", "Immediately end a customer's plan — stops ads, SpamBot-checks then frees their accounts, clears them from all queues."),
    ("/reconcile", "/reconcile", "Scan for customers missing from the queue despite being owed accounts, and auto-fix it."),
    ("/remove", "/remove [username or link]", "Remove a marketplace from the system."),
    ("/cofounder", "/cofounder @username", "Grant/manage co-founder (admin) access."),
    ("/addg", "/addg", "Add one or more marketplace groups (send usernames/links after)."),
    ("/add", "/add @m1 @m2 https://t.me/m3 ...", "Add marketplace groups directly, space-separated."),
    ("/addadbot", "/addadbot", "Add a new Ad Bot Account (interactive phone/code login)."),
    ("/addadbot", "/addadbot @username", "Assign a free Ad Bot Account directly to that customer, skipping the queue."),
    ("/canceladd", "/canceladd", "Cancel an in-progress /addadbot session."),
    ("/accounts", "/accounts", "List every Ad Bot Account in the system with its status."),
    ("/login", "/login +15551234567", "Get a fresh login code + saved 2FA password for an account."),
    ("/freeacc", "/freeacc", "List every free (unassigned, unrestricted) Ad Bot Account."),
    ("/occacc", "/occacc", "List every occupied Ad Bot Account, with its owner and slot."),
    ("/restricted", "/restricted", "List every restricted/banned Ad Bot Account (auto-rechecked daily)."),
    ("/removeno", "/removeno (number)", "Permanently delete an Ad Bot Account by ID — must be re-logged-in to use again."),
    ("/lowquality", "/lowquality", "List marketplaces auto-demoted for consistently burying/deleting posts."),
    ("/requality", "/requality (id)", "Give an auto-demoted marketplace another chance."),
    ("/checkall", "/checkall", "Immediately @SpamBot-check every occupied account at the same time (concurrent sweep)."),
    ("/temp1", "/temp1 @username", "Preview-only: shows exactly what a customer would receive if their account were replaced."),
    ("/free", "/free +15551234567", "Pull a number off its current customer, SpamBot-check it, and return it to the free pool if clean."),
    ("/oc", "/oc", "Show this list of every owner command."),
]

@router.message(Command("oc"))
async def cmd_owner_commands(message: Message):
    """Owner-only: lists every owner command with its usage."""
    if not store.is_admin(message.from_user.id):
        return
    import html as _html
    lines = ["<b>Owner Commands</b>", ""]
    for cmd, usage, desc in OWNER_COMMANDS:
        lines.append(f"<code>{_html.escape(usage)}</code>\n{_html.escape(desc)}\n")
    text = "\n".join(lines)
    if len(text) > 3900:
        # Telegram message length safety — split into chunks
        chunks = []
        current = "<b>Owner Commands</b>\n\n"
        for cmd, usage, desc in OWNER_COMMANDS:
            entry = f"<code>{_html.escape(usage)}</code>\n{_html.escape(desc)}\n\n"
            if len(current) + len(entry) > 3900:
                chunks.append(current)
                current = ""
            current += entry
        if current:
            chunks.append(current)
        for chunk in chunks:
            await message.reply(chunk, parse_mode="HTML")
    else:
        await message.reply(text, parse_mode="HTML")

@router.message(Command("lowquality"))
async def cmd_low_quality_marketplaces(message: Message):
    """Owner-only: lists marketplaces the system has automatically stopped
       posting to because they consistently bury/delete ads before anyone sees them."""
    if not store.is_admin(message.from_user.id):
        return
    rows = await db.get_low_quality_marketplaces()
    if not rows:
        await message.reply("No marketplaces have been auto-demoted — everything's posting visibly.")
        return
    lines = ["<b>Auto-Demoted (Low Visibility) Marketplaces</b>", ""]
    for r in rows:
        label = f"@{r['chat_username']}" if r["chat_username"] and not str(r["chat_username"]).lstrip("-").isdigit() else str(r["chat_id"])
        lines.append(f"ID {r['id']} — {label} — buried {r['buried_count']}/{r['checks']} checks")
    lines.append("")
    lines.append("These are automatically skipped by the posting rotation. Use /requality (id) to give one another chance.")
    await message.reply("\n".join(lines), parse_mode="HTML")

@router.message(Command("requality"))
async def cmd_requality_marketplace(message: Message):
    """Owner-only: resets an auto-demoted marketplace back to standard quality,
       clearing its stats and letting the rotation post to it again."""
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("Usage: /requality (marketplace ID number)\n\nSee IDs via /lowquality.")
        return
    marketplace_id = int(parts[1])
    await db.reset_marketplace_quality(marketplace_id)
    await message.reply(f"Marketplace ID {marketplace_id} reset to standard quality — it'll be included in posting rotations again.")
