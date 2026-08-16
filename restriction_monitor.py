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

# ---- Live failure-ratio notifier -----------------------------------------
# Tracks, per ad_account_id, which marketplaces are CURRENTLY failing (based on
# their most recent post attempt) with a ban/write-restriction error. Once that
# reaches FAILURE_RATIO_THRESHOLD of the account's eligible (non-low-quality)
# marketplaces, the owner gets a notify-only alert — no auto-replacement, the
# owner decides what to do (e.g. via the full sweep's Replace button below).
FAILURE_RATIO_THRESHOLD = 0.6
_failing_marketplaces = {}   # ad_account_id -> set of marketplace_id currently failing
_ratio_flagged = set()       # ad_account_id already notified for the current breach —
                              # cleared once the ratio drops back below threshold so a
                              # fresh breach later can notify again.

async def _eligible_marketplaces(ad_account_id: int):
    """Non-low-quality marketplaces in this account's active ad list — mirrors
       the same filtering engine.py's main rotation already applies."""
    existing_ad = await db.get_active_ad_for_account(ad_account_id)
    if not existing_ad:
        return []
    all_marketplaces = await db.get_list_marketplaces(existing_ad["marketplace_list_id"])
    return [m for m in all_marketplaces if m["quality_tier"] != "low"]

async def record_marketplace_ban(ad_account_id: int, marketplace_id: int):
    """Called on every post failure caused by a ban/write-restriction on a
       specific marketplace. Updates the live failing snapshot and notifies the
       owner (no auto-replace) once >=60% of eligible marketplaces are failing."""
    failing = _failing_marketplaces.setdefault(ad_account_id, set())
    failing.add(marketplace_id)

    if ad_account_id in _ratio_flagged:
        return  # already notified for this breach — don't spam repeatedly

    eligible = await _eligible_marketplaces(ad_account_id)
    if not eligible:
        return
    eligible_ids = {m["id"] for m in eligible}
    currently_failing_ids = failing & eligible_ids
    ratio = len(currently_failing_ids) / len(eligible)
    if ratio < FAILURE_RATIO_THRESHOLD:
        return

    _ratio_flagged.add(ad_account_id)
    asyncio.create_task(notify_owner_marketplace_failure_ratio(ad_account_id, currently_failing_ids, eligible))

def record_marketplace_success(ad_account_id: int, marketplace_id: int):
    """Called on every successful post. Clears that marketplace from the live
       failing snapshot, and — once the ratio drops back below threshold —
       clears the notify flag so a future breach can notify again."""
    failing = _failing_marketplaces.get(ad_account_id)
    if failing:
        failing.discard(marketplace_id)
    if ad_account_id in _ratio_flagged:
        asyncio.create_task(_maybe_unflag(ad_account_id))

async def _maybe_unflag(ad_account_id: int):
    eligible = await _eligible_marketplaces(ad_account_id)
    if not eligible:
        _ratio_flagged.discard(ad_account_id)
        return
    eligible_ids = {m["id"] for m in eligible}
    failing = _failing_marketplaces.get(ad_account_id, set()) & eligible_ids
    ratio = len(failing) / len(eligible)
    if ratio < FAILURE_RATIO_THRESHOLD:
        _ratio_flagged.discard(ad_account_id)

async def notify_owner_marketplace_failure_ratio(ad_account_id: int, failing_ids: set, eligible: list):
    """Notify-only alert: this account can't post to >=60% of its eligible
       marketplaces right now. No auto-replacement — use the full sweep's
       Replace button (or your own tools) if you decide to act on it."""
    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if not owner_id:
        return

    account = await db.get_ad_account_by_id(ad_account_id)
    target_uid, target_idx, target_name = _find_customer_slot(ad_account_id)

    failing_names = [m.get("chat_username") or str(m["id"]) for m in eligible if m["id"] in failing_ids]
    ratio_pct = round(100 * len(failing_ids) / len(eligible))

    lines = [
        f"⚠️ Ad Bot Account ID {ad_account_id} ({account['phone']}) can't post to "
        f"{ratio_pct}% of its marketplaces ({len(failing_ids)}/{len(eligible)}, low-quality ones excluded).",
        "",
        "Currently failing:",
    ]
    lines.extend(f"  • {n}" for n in failing_names[:20])
    if len(failing_names) > 20:
        lines.append(f"  ...and {len(failing_names) - 20} more")
    if target_uid is not None:
        lines.append(f"\nCustomer: user_id={target_uid}" + (f" — {target_name}" if target_name else ""))
    lines.append("\nThis is a notify-only alert — no automatic replacement was made.")

    rows = []
    if target_uid is not None:
        rows = [[
            {"text": "Notify Customer", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:yes"},
            {"text": "Don't Notify", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:no"},
        ]]
    try:
        await raw_api.send_message(owner_id, "\n".join(lines), rows)
    except Exception as e:
        print(f"[restriction_monitor] could not notify owner of marketplace failure ratio: {e}")

def _find_customer_slot(ad_account_id: int):
    """Returns (user_id, index, name) for whichever customer/slot currently
       holds this ad_account_id, or (None, None, None) if it's unassigned."""
    all_adbots = store.load_customer_adbots()
    for uid_str, bots in all_adbots.items():
        for i, bot in enumerate(bots):
            if bot.get("ad_account_id") == ad_account_id:
                return int(uid_str), i, bot.get("name")
    return None, None, None

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

# ---- Restart-proof stall detector ------------------------------------------
# Unlike the live failure-ratio tracker above (which resets to zero on every
# process restart and needs sustained uptime to accumulate a 60% breach), this
# checks a value persisted in the database: how long since this account's LAST
# real successful post. A total-failure account (ban, dead session, dead
# source channel, etc.) fails every single attempt from the start, so this
# catches it fast and survives restarts -- it doesn't need to "build up" state.
STALL_THRESHOLD_SECONDS = 20 * 60   # alert if no success in 20 min despite active attempts
STALL_RE_ALERT_COOLDOWN = 60 * 60   # don't re-alert on the same account more than once/hour

async def watch_for_stalled_accounts():
    while True:
        try:
            await _check_stalled_accounts_once()
        except Exception as e:
            print(f"[restriction_monitor] watch_for_stalled_accounts error: {e}")
        await asyncio.sleep(5 * 60)

async def _check_stalled_accounts_once():
    now_ts = __import__("time").time()
    active_ads = await db.get_active_advertisements()
    active_account_ids = {a["ad_account_id"] for a in active_ads}
    activity_rows = {r["ad_account_id"]: r for r in await db.get_all_account_activity()}

    for ad_account_id in active_account_ids:
        row = activity_rows.get(ad_account_id)
        if not row or not row["loop_started_at"]:
            continue  # loop hasn't recorded a start yet, nothing to check

        reference_time = row["last_success_at"] or row["loop_started_at"]
        elapsed = now_ts - reference_time
        if elapsed < STALL_THRESHOLD_SECONDS:
            continue

        last_alert = row["last_alert_at"]
        if last_alert and (now_ts - last_alert) < STALL_RE_ALERT_COOLDOWN:
            continue

        await db.mark_alert_sent(ad_account_id)
        asyncio.create_task(notify_owner_account_stalled(ad_account_id, elapsed))

async def notify_owner_account_stalled(ad_account_id: int, elapsed_seconds: float):
    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if not owner_id:
        return
    account = await db.get_ad_account_by_id(ad_account_id)
    target_uid, target_idx, target_name = _find_customer_slot(ad_account_id)
    elapsed_min = round(elapsed_seconds / 60)

    lines = [
        f"\u26a0\ufe0f Ad Bot Account ID {ad_account_id} ({account['phone']}) hasn't posted "
        f"successfully in {elapsed_min} minutes despite actively attempting.",
        "",
        "This usually means a full account restriction, dead session, or a dead source channel -- "
        "not just a few unreachable marketplaces.",
    ]
    if target_uid is not None:
        lines.append(f"\nCustomer: user_id={target_uid}" + (f" -- {target_name}" if target_name else ""))

    rows = []
    if target_uid is not None:
        rows = [[
            {"text": "Notify Customer", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:yes"},
            {"text": "Don't Notify", "callback_data": f"restrictdetected:{target_uid}:{target_idx}:no"},
        ]]
    try:
        await raw_api.send_message(owner_id, "\n".join(lines), rows)
    except Exception as e:
        print(f"[restriction_monitor] could not notify owner of stalled account: {e}")

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
        # Find which customer/slot owns this account (this is invoked directly — from
        # the full sweep's Replace button, or a queued replacement — not via any
        # automatic trigger; the reactive ban-streak auto-replace flow was removed)
        target_uid, target_idx, target_name = _find_customer_slot(old_account_id)
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
    await myadbot.fulfill_replacement(target_uid, target_idx, new_account["id"], ad_config, old_profile=old_profile, reason="restricted")

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

# ---- Full concurrent sweep: checks every occupied account via @SpamBot AT
# THE SAME TIME (not one-by-one, and not dependent on post-failure streaks),
# then asks the owner Replace/Ignore for anything flagged — separate from the
# reactive, auto-replacing flow above.
SWEEP_CONCURRENCY = 8  # cap simultaneous @SpamBot checks so this can't itself look like flooding

async def _sweep_check_one(account, semaphore):
    async with semaphore:
        try:
            reply = await check_via_spambot(account["id"])
        except Exception as e:
            print(f"[restriction_monitor] sweep check failed for account {account['id']}: {e}")
            return None
        if _spambot_indicates_restriction(reply):
            return (account, reply)
        return None

async def full_sweep_all_accounts():
    """Checks every occupied Ad Bot Account via @SpamBot concurrently. Anything
       that comes back restricted is reported to the owner with Replace/Ignore
       buttons — nothing is auto-replaced here, the owner decides (unlike the
       reactive post-failure flow above, which replaces immediately)."""
    accounts = await db.get_occupied_ad_accounts()
    if not accounts:
        return

    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if not owner_id:
        return

    semaphore = asyncio.Semaphore(SWEEP_CONCURRENCY)
    results = await asyncio.gather(*[_sweep_check_one(a, semaphore) for a in accounts])
    flagged = [r for r in results if r]

    if not flagged:
        return  # clean sweep — don't message the owner when there's nothing to act on

    for account, spambot_reply in flagged:
        uid, idx, name = _find_customer_slot(account["id"])
        owner_label = f"user_id={uid}" if uid is not None else "(unassigned account)"
        slot_label = f" — slot {name or 'Adbot'} #{idx + 1}" if idx is not None else ""
        text = (
            f"⚠️ Full sweep check: Ad Bot Account ID {account['id']} ({account['phone']}) "
            f"looks restricted.\n\nCustomer: {owner_label}{slot_label}\n\n"
            f"@SpamBot says:\n{spambot_reply}"
        )
        rows = [[
            {"text": "Replace", "callback_data": f"sweepflag:{account['id']}:replace"},
            {"text": "Ignore", "callback_data": f"sweepflag:{account['id']}:ignore"},
        ]]
        try:
            await raw_api.send_message(owner_id, text, rows)
        except Exception as e:
            print(f"[restriction_monitor] could not send sweep alert: {e}")

@router.callback_query(F.data.startswith("sweepflag:"))
async def cb_sweep_flag(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    _, account_id_str, choice = callback.data.split(":")
    account_id = int(account_id_str)

    if choice == "ignore":
        try:
            await callback.message.edit_text(callback.message.text + "\n\n— Ignored, no action taken.")
        except Exception:
            pass
        await callback.answer("Ignored.")
        return

    try:
        await callback.message.edit_text(callback.message.text + "\n\n— Replacing now…")
    except Exception:
        pass
    admins = store.load_admins()
    owner_id = admins.get("owner_id") or callback.from_user.id
    uid, idx, name = _find_customer_slot(account_id)
    await do_replacement(account_id, owner_id, uid, idx, name)
    await callback.answer("Replacement started.")

SWEEP_INTERVAL_SECONDS = 6 * 60 * 60  # every 6 hours

async def sweep_loop():
    while True:
        try:
            await full_sweep_all_accounts()
        except Exception as e:
            print(f"[restriction_monitor] full sweep failed: {e}")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
