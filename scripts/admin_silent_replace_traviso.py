"""
One-off admin action: manually replace @traviso's single adbot account with a
specific pre-chosen free-pool account, following the exact same steps /change
uses (myadbot.fulfill_replacement) -- stop old ad, capture old profile,
mark old account banned, apply name/bio/photo to the new account, recreate
the ad, join the new account to all marketplaces -- but WITHOUT sending the
customer-facing "your account was replaced" notification for this one run.

This does NOT modify fulfill_replacement or admin_commands.py at all, so
every other use of /change (and the automated restriction_monitor
replacement flow) still notifies customers exactly as before -- the
suppression here is scoped to this single script run only.

Safety checks built in:
  - Aborts if @traviso doesn't have EXACTLY 1 adbot (so it can't accidentally
    pick the wrong slot for a customer with multiple).
  - Aborts if the target phone number isn't found, or isn't status='free'.

Run once, from bot_project_clean, while the bot is live (same as /change --
no need to stop the service first):

    python3 scripts/admin_silent_replace_traviso.py
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import myadbot
import content_store as store
import engine
from aiogram import Bot

TARGET_USERNAME = "traviso"
NEW_ACCOUNT_PHONE = "+2348165330647"


async def main():
    target_uid = store.get_uid_by_username(TARGET_USERNAME)
    if not target_uid:
        print(f"@{TARGET_USERNAME} hasn't started the bot yet -- aborting.")
        return

    adbots = store.get_customer_adbots(target_uid)
    if not adbots:
        print(f"@{TARGET_USERNAME} has no Ad Bot Accounts -- aborting.")
        return
    if len(adbots) != 1:
        print(f"@{TARGET_USERNAME} has {len(adbots)} adbots, expected exactly 1 -- "
              f"aborting to be safe rather than guess which slot. Run /change "
              f"manually and pick the right slot if this is intentional.")
        return

    idx = 0
    bot_slot = adbots[idx]
    old_account_id = bot_slot["ad_account_id"]
    print(f"Old account: id={old_account_id}")

    new_account = await db.get_ad_account_by_phone(NEW_ACCOUNT_PHONE)
    if not new_account:
        print(f"No ad_accounts row found for phone {NEW_ACCOUNT_PHONE} -- aborting.")
        return
    if new_account["status"] != "free":
        print(f"Account {new_account['id']} ({NEW_ACCOUNT_PHONE}) is not free "
              f"(status={new_account['status']}) -- aborting.")
        return
    new_account_id = new_account["id"]
    print(f"New account: id={new_account_id}, phone={NEW_ACCOUNT_PHONE}, confirmed free.")

    # --- same steps as admin_commands._do_change ---
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
        print(f"Stopped old ad id={existing_ad['id']}")

    old_profile = {"name": store.slot_display_name(bot_slot, idx), "bio": None, "photo_bytes": None}
    try:
        old_client = await engine.get_client(old_account_id)
        me = await old_client.get_me()
        old_profile["bio"] = getattr(me, "about", None)
        photo_buf = io.BytesIO()
        downloaded = await old_client.download_profile_photo(me, file=photo_buf)
        if downloaded:
            photo_buf.seek(0)
            old_profile["photo_bytes"] = photo_buf
    except Exception as e:
        print(f"Could not capture old profile (continuing anyway): {e}")

    await db.mark_ad_account_status_no_fulfill(old_account_id, "banned")
    print(f"Marked old account {old_account_id} as banned.")

    # --- suppress just the customer-facing notification, just for this run ---
    original_send_message = Bot.send_message
    async def _quiet_send_message(self, chat_id, *args, **kwargs):
        if chat_id == target_uid:
            print(f"(suppressed customer notification to uid={target_uid} as requested)")
            return None
        return await original_send_message(self, chat_id, *args, **kwargs)
    Bot.send_message = _quiet_send_message

    try:
        await myadbot.fulfill_replacement(
            target_uid, idx, new_account_id, ad_config,
            old_profile=old_profile, reason="banned",
        )
    finally:
        Bot.send_message = original_send_message

    print("Done. Replacement complete, customer was not notified.")


if __name__ == "__main__":
    asyncio.run(main())
