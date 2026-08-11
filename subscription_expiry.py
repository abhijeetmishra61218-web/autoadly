"""
AutoAdly - Subscription expiry: warns customers 3 days before expiry,
and automatically stops ads + reclaims Ad Bot Accounts back to the pool
the moment a subscription actually expires (freed accounts auto-fulfill
any queued replacements/new requests via the existing chain).
"""

import time
import asyncio
from aiogram import Bot

import content_store as store
import database as db
import config

WARNING_WINDOW_SECONDS = 3 * 24 * 60 * 60  # warn 3 days before expiry
CHECK_INTERVAL_SECONDS = 60 * 60  # check hourly

async def _notify(user_id, text):
    try:
        bot = Bot(token=config.BOT_TOKEN)
        await bot.send_message(user_id, text, parse_mode="HTML")
        await bot.session.close()
    except Exception as e:
        print(f"[subscription_expiry] could not notify user {user_id}: {e}")

async def _notify_owner(text):
    admins = store.load_admins()
    owner_id = admins.get("owner_id")
    if not owner_id:
        return
    await _notify(owner_id, text)

async def release_customer_accounts(user_id, plan_name, source="expired"):
    """Stops ads and releases a customer's Ad Bot Accounts, but only returns
       a clean account to the free pool after confirming via @SpamBot that
       it's not actually restricted/banned — a restricted account is held
       back instead of being handed to the next customer. Preserves each
       slot's name/bio/photo so a returning customer's next account in the
       same slot automatically looks the same as before. Notifies the owner
       throughout. Returns (freed_count, restricted_count)."""
    import restriction_monitor as rm

    username = store.get_username_by_uid(user_id)
    label = f"@{username}" if username else f"user_id={user_id}"

    adbots = store.get_customer_adbots(user_id)
    account_ids = [b["ad_account_id"] for b in adbots if b.get("ad_account_id") is not None]

    if account_ids:
        await _notify_owner(
            f"{label}'s <b>{plan_name}</b> plan {source}. Checking {len(account_ids)} "
            f"Ad Bot Account(s) via @SpamBot before releasing them..."
        )

    freed = 0
    restricted = 0
    for bot in adbots:
        account_id = bot.get("ad_account_id")
        if account_id is None:
            continue

        existing_ad = await db.get_active_ad_for_account(account_id)
        if existing_ad:
            await db.stop_advertisement(existing_ad["id"])

        spambot_reply = await rm.check_via_spambot(account_id)
        if rm._spambot_indicates_restriction(spambot_reply):
            await db.mark_ad_account_status_no_fulfill(account_id, "restricted")
            restricted += 1
            await _notify_owner(
                f"Account ID {account_id} ({bot.get('name') or 'unnamed'}, from {label}) came back "
                f"RESTRICTED on @SpamBot check — held back, NOT returned to the free pool.\n\n{spambot_reply}"
            )
        else:
            await db.mark_ad_account_status(account_id, "free")
            freed += 1
            await _notify_owner(
                f"Account ID {account_id} ({bot.get('name') or 'unnamed'}, from {label}) is clean — "
                f"released to the free pool."
            )

    # Preserve slot identity (name/bio/photo) but clear ad_account_id, so a
    # returning customer's next account in the same slot looks the same.
    store.free_customer_slots(user_id)

    await _notify_owner(
        f"Finished releasing {label}'s accounts: {freed} freed (auto-assigned if anyone was "
        f"waiting), {restricted} held back as restricted."
    )

    return freed, restricted

async def check_all_subscriptions():
    subs = store.load_subscriptions()
    now = time.time()

    for uid_str, sub in list(subs.items()):
        user_id = int(uid_str)

        if sub.get("reclaimed"):
            continue  # already handled, nothing more to do for this subscription

        if sub["expiry"] <= now:
            plan = store.get_plan(sub["plan_id"])
            plan_name = plan["name"] if plan else sub["plan_id"]

            await release_customer_accounts(user_id, plan_name, source="expired")

            store.mark_subscription_flag(user_id, "reclaimed", True)
            await _notify(
                user_id,
                f"Your <b>{plan_name}</b> subscription has expired. Your advertisements have been stopped "
                f"and your Ad Bot Accounts have been released.\n\nTap Buy Ad Bot to renew and get set up again."
            )
            continue

        if not sub.get("notified_soon") and (sub["expiry"] - now) <= WARNING_WINDOW_SECONDS:
            plan = store.get_plan(sub["plan_id"])
            plan_name = plan["name"] if plan else sub["plan_id"]
            days_left = max(0, int((sub["expiry"] - now) / 86400))
            store.mark_subscription_flag(user_id, "notified_soon", True)
            await _notify(
                user_id,
                f"Your <b>{plan_name}</b> subscription expires in {days_left} day(s). "
                f"Renew via Buy Ad Bot to avoid any interruption to your advertisements."
            )

async def expiry_loop():
    while True:
        try:
            await check_all_subscriptions()
        except Exception as e:
            print(f"[subscription_expiry] check failed: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
