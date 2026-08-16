"""
AutoAdly - "My Ad Bot" dashboard, account management, quota-based requests
"""

import time
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message

import raw_api
import content_store as store
import database as db
import engine
import config
import profile_updater as pu

router = Router()

EDIT_PENDING = {}

def has_active_subscription(user_id):
    sub = store.get_subscription(user_id)
    return bool(sub and sub.get("expiry", 0) > time.time())

def _get_quota(user_id):
    sub = store.get_subscription(user_id)
    if not sub:
        return 0
    plan = store.get_plan(sub["plan_id"])
    return plan.get("max_ad_accounts", 1) if plan else 1

def _dashboard_rows(user_id):
    emojis = store.load_action_emojis()
    rows = [
        [{"text": "Set Advertisement", "callback_data": "myad:set_ad", "emoji_id": emojis.get("dash_set_ad")}],
        [{"text": "Live Advertisement", "callback_data": "myad:live", "emoji_id": emojis.get("dash_live")}],
        [{"text": "Advertisement Logs", "callback_data": "myad:logs", "emoji_id": emojis.get("dash_logs")}],
        [{"text": "Manage Ad Bot", "callback_data": "myad:manage", "emoji_id": emojis.get("dash_manage")}],
        [{"text": "Subscription", "callback_data": "myad:subscription", "emoji_id": emojis.get("dash_subscription")}],
    ]
    rows.append([{"text": "Back to Home", "callback_data": "start:home", "emoji_id": store.load_action_emojis().get("back_to_home_button")}])
    return rows

@router.callback_query(F.data == "myadbot:open")
async def cb_open_myadbot(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not has_active_subscription(user_id):
        await callback.answer("You don't have an active subscription yet. Tap Buy Ad Bot to get started.", show_alert=True)
        return

    adbots = store.get_customer_adbots(user_id)
    quota = _get_quota(user_id)
    total = len(adbots)
    working = 0
    for bot in adbots:
        if await db.has_active_ad(bot["ad_account_id"]):
            working += 1
    inactive = total - working

    text = (
        f"<b>My Ad Bot</b>\n\n"
        f"<b>Total Ad Bot Accounts :</b> {total}/{quota}\n"
        f"<b>Active Ad Bot Accounts :</b> {working}\n"
        f"<b>Inactive Ad Bot Accounts :</b> {inactive}"
    )
    rows = _dashboard_rows(user_id)
    if store.is_admin(user_id):
        rows.insert(0, [{"text": "Set Dashboard Photo", "callback_data": "myadbot:set_dash_photo"}])

    photo = store.get_dashboard_image()
    await raw_api.render(callback.message.chat.id, callback.message.message_id, text, rows, photo=photo)
    await callback.answer()

async def request_accounts_for_customer(user_id, chat_id, quota):
    """Called right after purchase (or renewal). `quota` is the customer's TOTAL
       plan quota (not just the missing count) — this creates every slot up front
       (e.g. all 5 for Elite) so they're all visible and editable in Manage Ad Bot
       immediately, whether or not an account is filled in yet. Assigns instantly
       from any free accounts; any slots left empty just sit there ready to be
       customized (name/bio/photo) via Manage Ad Bot until stock arrives."""
    store.ensure_customer_slots(user_id, quota)
    assigned_any = False
    while True:
        idx = store.get_next_empty_slot_index(user_id)
        if idx is None:
            break
        account = await db.get_free_ad_account()
        if not account:
            break
        await _assign_account(chat_id, None, user_id, account["id"], send_new=True)
        assigned_any = True

    remaining = sum(1 for s in store.get_customer_adbots(user_id) if s.get("ad_account_id") is None)
    if remaining > 0:
        for _ in range(remaining):
            store.queue_pending_account_request(user_id)
        try:
            await raw_api.send_message(
                chat_id,
                f"You have {remaining} more Ad Bot Account(s) coming once stock is available.\n\n"
                f"You can already set their name, bio, and photo now in Manage Ad Bot — "
                f"whatever you set will be applied automatically the moment each account is ready.",
                [[{"text": "Go to Manage Ad Bot", "callback_data": "myad:manage"}]],
            )
        except Exception as e:
            print(f"[request_accounts_for_customer] could not send queued notice: {e}")

    return assigned_any

async def _assign_account(chat_id, msg_id, user_id, account_id, send_new=False):
    await db.mark_ad_account_status_no_fulfill(account_id, "occupied")

    idx = store.get_next_empty_slot_index(user_id)
    if idx is None:
        # No pre-existing empty slot. Only fall back to appending a brand new
        # one if the customer is genuinely still under their plan quota (this
        # covers quota tracking being out of sync) — never hand out more
        # accounts than they're actually paying for. Without this check, a
        # stale/ghost queue entry could keep silently bolting extra accounts
        # onto a customer beyond their plan (e.g. 2 accounts on a 1-account plan).
        quota = _get_quota(user_id)
        current_total = len(store.get_customer_adbots(user_id))
        if current_total >= quota:
            await db.mark_ad_account_status_no_fulfill(account_id, "free")
            print(f"[_assign_account] refused to give user {user_id} an account beyond their quota ({quota}); account {account_id} returned to the free pool.")
            return
        store.add_customer_adbot(user_id, None, account_id)
        adbots = store.get_customer_adbots(user_id)
        idx = len(adbots) - 1
        slot = adbots[idx]
    else:
        slot = store.get_customer_adbots(user_id)[idx]

    display_name = store.slot_display_name(slot, idx)
    bio = slot.get("bio") or ""
    photo_file_id = slot.get("photo_file_id")

    client = await engine.get_client(account_id)
    await pu.update_name_bio(client, display_name, bio)
    await pu.update_username(client, None)
    if photo_file_id:
        try:
            bot_api = Bot(token=config.BOT_TOKEN)
            await pu.update_photo(client, bot_api, photo_file_id)
            await bot_api.session.close()
        except Exception as e:
            print(f"[_assign_account] photo apply failed: {e}")

    store.fill_slot_with_account(user_id, idx, account_id)
    if not slot.get("name"):
        store.rename_customer_adbot(user_id, idx, display_name)

    text = f"<b>{display_name}</b> is ready! Go to Manage Ad Bot to customize it, or Set Advertisement to start posting."
    rows = [[{"text": "Back to Home", "callback_data": "start:home", "emoji_id": store.load_action_emojis().get("back_to_home_button")}]]
    if msg_id and not send_new:
        await raw_api.render(chat_id, msg_id, text, rows)
    else:
        await raw_api.send_message(chat_id, text, rows)

@router.callback_query(F.data == "myadbot:set_dash_photo")
async def cb_set_dash_photo(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    EDIT_PENDING[callback.from_user.id] = {"step": "await_dash_photo"}
    await callback.message.answer("Send the new photo for the My Ad Bot dashboard, or send 0 to remove it.")
    await callback.answer()

@router.callback_query(F.data == "myad:subscription")
async def cb_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    sub = store.get_subscription(user_id)
    if not sub:
        await callback.answer("No subscription found.", show_alert=True)
        return
    plan = store.get_plan(sub["plan_id"])
    plan_name = plan["name"] if plan else sub["plan_id"]
    purchase_str = time.strftime("%Y-%m-%d", time.localtime(sub["purchase_date"]))
    expiry_str = time.strftime("%Y-%m-%d", time.localtime(sub["expiry"]))
    remaining_days = max(0, int((sub["expiry"] - time.time()) / 86400))
    adbots = store.get_customer_adbots(user_id)

    text = (
        f"<b>Subscription</b>\n\n"
        f"Plan: {plan_name}\n"
        f"Purchase Date: {purchase_str}\n"
        f"Expiry Date: {expiry_str}\n"
        f"Remaining: {remaining_days} day(s)\n"
        f"Ad Bot Accounts: {len(adbots)}/{_get_quota(user_id)}"
    )
    await raw_api.render(callback.message.chat.id, callback.message.message_id, text, [[{"text": "Back", "callback_data": "myadbot:open"}]])
    await callback.answer()

@router.callback_query(F.data == "myad:manage")
async def cb_manage(callback: CallbackQuery):
    user_id = callback.from_user.id
    adbots = store.get_customer_adbots(user_id)
    rows = []
    for i, slot in enumerate(adbots):
        label = store.slot_display_name(slot, i)
        if slot.get("ad_account_id") is None:
            label += " (pending)"
        rows.append([{"text": label, "callback_data": f"myad:manage_one:{i}"}])
    rows.append([{"text": "Back", "callback_data": "myadbot:open"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "<b>Manage Ad Bot</b>\n\nSelect an account:", rows)
    await callback.answer()

def _account_edit_rows(idx, assigned=True):
    rows = [
        [{"text": "Edit Name", "callback_data": f"myad:editname:{idx}"}],
        [{"text": "Edit Bio", "callback_data": f"myad:editbio:{idx}"}],
    ]
    if assigned:
        rows.append([{"text": "Edit Username", "callback_data": f"myad:editusername:{idx}"}])
    rows.append([{"text": "Edit Photo", "callback_data": f"myad:editphoto:{idx}"}])
    rows.append([{"text": "Copy Your Profile", "callback_data": f"myad:copyprofile:{idx}"}])
    rows.append([{"text": "Back", "callback_data": "myad:manage"}])
    return rows

@router.callback_query(F.data.startswith("myad:copyprofile:"))
async def cb_copy_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    bot = adbots[idx]

    tg_user = callback.from_user
    display_name = f"{tg_user.first_name or 'User'} #{idx + 1}"
    bio = ""
    is_assigned = bot.get("ad_account_id") is not None

    file_id = None
    bot_api = Bot(token=config.BOT_TOKEN)
    try:
        user_photos = await bot_api.get_user_profile_photos(user_id, limit=1)
        if user_photos.total_count > 0:
            file_id = user_photos.photos[0][-1].file_id
    except Exception as e:
        print(f"[copy_profile] photo fetch failed: {e}")

    if not is_assigned:
        store.rename_customer_adbot(user_id, idx, display_name)
        store.set_slot_bio(user_id, idx, bio)
        if file_id:
            store.set_slot_photo(user_id, idx, file_id)
        await bot_api.session.close()
        await callback.answer("Profile saved — it will be applied automatically once an Ad Bot Account is assigned.", show_alert=True)
        return

    client = await engine.get_client(bot["ad_account_id"])
    ok_name = await pu.update_name_bio(client, display_name, bio)
    photo_ok = False
    try:
        if file_id:
            photo_ok = await pu.update_photo(client, bot_api, file_id)
    except Exception as e:
        print(f"[copy_profile] photo copy failed: {e}")
    await bot_api.session.close()
    await callback.answer("Profile copied to your Ad Bot Account." if ok_name else "Copy partially failed, please try again.", show_alert=True)

@router.callback_query(F.data.startswith("myad:manage_one:"))
async def cb_manage_one(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    slot = adbots[idx]
    display_name = store.slot_display_name(slot, idx)

    if slot.get("ad_account_id") is None:
        text = f"<b>{display_name}</b>\n\nNot yet assigned an Ad Bot Account. Set the name/bio/photo now — it will be applied automatically the moment one becomes available."
    else:
        account = await db.get_ad_account_by_id(slot["ad_account_id"])
        phone = account["phone"] if account else "unknown"
        text = f"<b>{display_name}</b>\n\nAccount: {phone}"

    await raw_api.render(callback.message.chat.id, callback.message.message_id, text, _account_edit_rows(idx, assigned=slot.get("ad_account_id") is not None))
    await callback.answer()

@router.callback_query(F.data.startswith("myad:editname:"))
async def cb_editname(callback: CallbackQuery):
    idx = int(callback.data.split(":", 2)[2])
    EDIT_PENDING[callback.from_user.id] = {"step": "await_edit_name", "index": idx}
    await callback.message.answer("Send the new name for this Ad Bot Account.")
    await callback.answer()

@router.callback_query(F.data.startswith("myad:editbio:"))
async def cb_editbio(callback: CallbackQuery):
    idx = int(callback.data.split(":", 2)[2])
    EDIT_PENDING[callback.from_user.id] = {"step": "await_edit_bio", "index": idx}
    await callback.message.answer("Send the new bio for this Ad Bot Account.")
    await callback.answer()

@router.callback_query(F.data.startswith("myad:editusername:"))
async def cb_editusername(callback: CallbackQuery):
    idx = int(callback.data.split(":", 2)[2])
    EDIT_PENDING[callback.from_user.id] = {"step": "await_edit_username", "index": idx}
    await callback.message.answer("Send the new username for this Ad Bot Account (no @).")
    await callback.answer()

@router.callback_query(F.data.startswith("myad:editphoto:"))
async def cb_editphoto(callback: CallbackQuery):
    idx = int(callback.data.split(":", 2)[2])
    EDIT_PENDING[callback.from_user.id] = {"step": "await_edit_photo", "index": idx}
    await callback.message.answer("Send the new photo for this Ad Bot Account.")
    await callback.answer()

@router.message(F.text, ~F.text.startswith("/"), F.from_user.id.in_(EDIT_PENDING.keys()))
async def on_edit_text(message: Message):
    user_id = message.from_user.id
    pending = EDIT_PENDING.get(user_id)
    if not pending:
        return
    step = pending["step"]

    if step == "await_dash_photo":
        if message.text.strip() == "0":
            store.set_dashboard_image(None)
            EDIT_PENDING.pop(user_id, None)
            await message.reply("Dashboard photo removed.")
        return

    idx = pending.get("index")
    adbots = store.get_customer_adbots(user_id)
    if idx is None or idx >= len(adbots):
        EDIT_PENDING.pop(user_id, None)
        return
    slot = adbots[idx]
    is_assigned = slot.get("ad_account_id") is not None
    client = await engine.get_client(slot["ad_account_id"]) if is_assigned else None

    if step == "await_edit_name":
        new_name = message.text.strip()
        store.rename_customer_adbot(user_id, idx, new_name)
        EDIT_PENDING.pop(user_id, None)
        if is_assigned:
            display_name = store.slot_display_name(store.get_customer_adbots(user_id)[idx], idx)
            ok = await pu.update_name_bio(client, display_name, slot.get("bio") or "")
            await message.reply("Name updated." if ok else "Name saved, but live update failed — please try again later.")
        else:
            await message.reply("Name saved — it will be applied automatically once an Ad Bot Account is assigned.")

    elif step == "await_edit_bio":
        bio = message.text.strip()
        store.set_slot_bio(user_id, idx, bio)
        EDIT_PENDING.pop(user_id, None)
        if is_assigned:
            display_name = store.slot_display_name(store.get_customer_adbots(user_id)[idx], idx)
            ok = await pu.update_name_bio(client, display_name, bio)
            await message.reply("Bio updated." if ok else "Bio saved, but live update failed — please try again later.")
        else:
            await message.reply("Bio saved — it will be applied automatically once an Ad Bot Account is assigned.")

    elif step == "await_edit_username":
        if not is_assigned:
            EDIT_PENDING.pop(user_id, None)
            await message.reply("This account isn't assigned yet — username can only be set once it's active.")
            return
        desired = message.text.strip().lstrip("@")
        result = await pu.update_username(client, desired)
        EDIT_PENDING.pop(user_id, None)
        if result:
            await message.reply(f"Username updated to @{result}.")
        else:
            await message.reply("Could not set that username (may be taken). Please try a different one.")

@router.message(F.photo, F.from_user.id.in_(EDIT_PENDING.keys()))
async def on_edit_photo(message: Message):
    user_id = message.from_user.id
    pending = EDIT_PENDING.get(user_id)
    if not pending:
        return

    if pending["step"] == "await_dash_photo":
        store.set_dashboard_image(message.photo[-1].file_id)
        EDIT_PENDING.pop(user_id, None)
        await message.reply("Dashboard photo updated.")
        return

    if pending["step"] != "await_edit_photo":
        return
    idx = pending.get("index")
    adbots = store.get_customer_adbots(user_id)
    if idx is None or idx >= len(adbots):
        EDIT_PENDING.pop(user_id, None)
        return
    bot = adbots[idx]
    client = await engine.get_client(bot["ad_account_id"])
    bot_api = Bot(token=config.BOT_TOKEN)
    ok = await pu.update_photo(client, bot_api, message.photo[-1].file_id)
    await bot_api.session.close()
    EDIT_PENDING.pop(user_id, None)
    await message.reply("Photo updated." if ok else "Photo update failed, please try again later.")

@router.callback_query(F.data == "myad:logs")
async def cb_logs(callback: CallbackQuery):
    user_id = callback.from_user.id
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await callback.answer("You don't have any Ad Bot Accounts yet.", show_alert=True)
        return
    if len(adbots) == 1:
        await _logs_for_account(callback.message.chat.id, callback.message.message_id, adbots[0]["ad_account_id"])
        await callback.answer()
        return
    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"dashlogs:acct:{i}"}] for i, bot in enumerate(adbots)]
    rows.append([{"text": "Back", "callback_data": "myadbot:open"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "<b>Advertisement Logs</b>\n\nWhich Ad Bot Account's logs do you want to see?", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("dashlogs:acct:"))
async def cb_dashboard_logs_account(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots) or adbots[idx].get("ad_account_id") is None:
        await callback.answer("That account no longer exists.", show_alert=True)
        return
    await _logs_for_account(callback.message.chat.id, callback.message.message_id, adbots[idx]["ad_account_id"])
    await callback.answer()


@router.callback_query(F.data == "myad:live")
async def cb_live_ads(callback: CallbackQuery):
    user_id = callback.from_user.id
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await callback.answer("You don't have any Ad Bot Accounts yet.", show_alert=True)
        return
    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"myad:live_one:{i}"}] for i, bot in enumerate(adbots)]
    rows.append([{"text": "Back", "callback_data": "myadbot:open"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "<b>Live Advertisement</b>\n\nSelect an account:", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("myad:live_one:"))
async def cb_live_one(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    bot = adbots[idx]
    ad = await db.get_active_ad_for_account(bot["ad_account_id"])

    if not ad:
        text = f"<b>{bot['name']}</b>\n\nNo advertisement is currently running on this account."
        rows = [
            [{"text": "Set Advertisement", "callback_data": "myad:set_ad"}],
            [{"text": "Back", "callback_data": "myad:live"}],
        ]
    else:
        link = f"https://t.me/c/{str(ad['source_chat_id'])[4:]}/{ad['source_message_id']}" if not ad["source_username"] else f"https://t.me/{ad['source_username']}/{ad['source_message_id']}"
        text = f"<b>{bot['name']}</b>\n\n<b>Currently Running This Ad :</b> {link}"
        rows = [
            [{"text": "Change Ad", "callback_data": f"myad:live_change:{idx}"}],
            [{"text": "Stop Ad", "callback_data": f"myad:live_stop:{idx}"}],
            [{"text": "Back", "callback_data": "myad:live"}],
        ]

    await raw_api.render(callback.message.chat.id, callback.message.message_id, text, rows)
    await callback.answer()

@router.callback_query(F.data.startswith("myad:live_stop:"))
async def cb_live_stop(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    bot = adbots[idx]
    ad = await db.get_active_ad_for_account(bot["ad_account_id"])
    if ad:
        await db.stop_advertisement(ad["id"])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, f"Advertisement stopped on <b>{bot['name']}</b>.", [[{"text": "Back", "callback_data": "myad:live"}]])
    await callback.answer()

@router.callback_query(F.data.startswith("myad:live_change:"))
async def cb_live_change(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    bot = adbots[idx]

    import adwizard
    existing = await db.get_active_ad_for_account(bot["ad_account_id"])
    pending = {"step": "await_link", "ad_account_id": bot["ad_account_id"], "ad_bot_name": bot["name"]}
    if existing:
        pending["existing_ad_id"] = existing["id"]
    adwizard.WIZARD_PENDING[user_id] = pending

    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        f"Send the new advertisement message link for <b>{bot['name']}</b>.\n\nExample: https://t.me/yourchannel/123",
        [[{"text": "Cancel", "callback_data": "myadbot:open"}]],
    )
    await callback.answer()


async def fulfill_replacement(user_id, index, new_account_id, ad_config, old_profile=None):
    """Reassigns a customer's banned Ad Bot Account slot to a fresh account.
       Uses the SLOT's own stored bio/photo (set via Manage Ad Bot) as the source
       of truth — always correctly numbered #N based on the slot's real index.
       old_profile (captured live from the restricted account at detection time)
       is only used as a FALLBACK when the slot itself has no saved bio/photo,
       so a customer's own Manage Ad Bot edits always win over a stale copy."""
    await db.mark_ad_account_status_no_fulfill(new_account_id, "occupied")
    store.set_customer_adbot_account(user_id, index, new_account_id)

    adbots = store.get_customer_adbots(user_id)
    slot = adbots[index] if index < len(adbots) else {"name": None}
    display_name = store.slot_display_name(slot, index)
    bio = slot.get("bio") or (old_profile.get("bio") if old_profile else None) or ""

    client = await engine.get_client(new_account_id)
    await pu.update_name_bio(client, display_name, bio)
    await pu.update_username(client, None)

    photo_file_id = slot.get("photo_file_id")
    if photo_file_id:
        try:
            bot_api = Bot(token=config.BOT_TOKEN)
            await pu.update_photo(client, bot_api, photo_file_id)
            await bot_api.session.close()
        except Exception as e:
            print(f"[fulfill_replacement] slot photo apply failed: {e}")
    elif old_profile and old_profile.get("photo_bytes"):
        await pu.update_photo_from_bytes(client, old_profile["photo_bytes"])

    if ad_config:
        await db.create_advertisement(
            new_account_id, ad_config["source_chat_id"], ad_config["source_message_id"],
            ad_config["category"], ad_config["marketplace_list_id"],
            source_username=ad_config.get("source_username"),
        )

    try:
        bot_api = Bot(token=config.BOT_TOKEN)
        text = f"Your banned Ad Bot Account has been replaced! <b>{display_name}</b> is ready"
        text += " and your advertisement is live again." if ad_config else "."
        await bot_api.send_message(user_id, text, parse_mode="HTML")
        await bot_api.session.close()
    except Exception as e:
        print(f"[fulfill_replacement] could not notify customer: {e}")


from aiogram.filters import Command

async def _logs_for_account(chat_id, msg_id, ad_account_id, send_new=False):
    logs = await db.get_recent_logs_for_account(ad_account_id, minutes=15)
    if not logs:
        text = "<b>Advertisement Logs</b>\n\nNo successful posts in the last 15 minutes yet."
    else:
        lines = ["<b>Advertisement Logs</b>", "(last 15 minutes)", ""]
        for log in logs:
            t = time.strftime("%H:%M:%S", time.localtime(log["posted_at"]))
            name = log["chat_username"] or "unknown"
            link = log["message_link"]
            lines.append(f"<b>{name}</b> — {t}\n{link}\n")
        text = "\n".join(lines)
    rows = [[{"text": "Back", "callback_data": "myadbot:open"}]]
    if msg_id and not send_new:
        await raw_api.render(chat_id, msg_id, text, rows)
    else:
        await raw_api.send_message(chat_id, text, rows)

@router.message(Command("logs"))
async def cmd_logs(message: Message):
    user_id = message.from_user.id
    if not has_active_subscription(user_id):
        await message.reply("Your subscription has expired. Tap Buy Ad Bot to renew and get set up again.")
        return
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await message.reply("You don't have any Ad Bot Accounts yet.")
        return
    if len(adbots) == 1:
        await _logs_for_account(message.chat.id, None, adbots[0]["ad_account_id"], send_new=True)
        return
    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"quicklogs:acct:{i}"}] for i, bot in enumerate(adbots)]
    await raw_api.send_message(message.chat.id, "Which Ad Bot Account's logs do you want to see?", rows)

@router.callback_query(F.data.startswith("quicklogs:acct:"))
async def cb_quicklogs_account(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    await _logs_for_account(callback.message.chat.id, callback.message.message_id, adbots[idx]["ad_account_id"])
    await callback.answer()

@router.message(Command("ad"))
async def cmd_ad(message: Message):
    user_id = message.from_user.id
    if not has_active_subscription(user_id):
        await message.reply("Your subscription has expired. Tap Buy Ad Bot to renew and get set up again.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: /ad <message link>\n\nExample: /ad https://t.me/yourchannel/5")
        return
    link = parts[1].strip()

    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await message.reply("You don't have an Ad Bot Account yet.")
        return

    import adwizard
    parsed = adwizard._parse_ad_link(link)
    if not parsed:
        await message.reply("That doesn't look like a valid Telegram message link.")
        return
    username, internal_id, msg_id = parsed

    pending = {"step": "choose_account", "username": username, "internal_id": internal_id, "msg_id": msg_id}

    if len(adbots) == 1:
        bot = adbots[0]
        pending["ad_account_id"] = bot["ad_account_id"]
        pending["ad_bot_name"] = bot["name"]
        existing = await db.get_active_ad_for_account(bot["ad_account_id"])
        if existing:
            pending["existing_ad_id"] = existing["id"]
        pending["step"] = "choose_category"
        adwizard.WIZARD_PENDING[user_id] = pending

        rows = []
        row = []
        for cat in adwizard.CATEGORIES:
            emoji_id = store.get_category_emoji(cat)
            btn = {"text": cat, "callback_data": f"adwiz:cat:{cat}"}
            if emoji_id:
                btn["emoji_id"] = emoji_id
            row.append(btn)
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([{"text": "Cancel", "callback_data": "myadbot:open"}])
        await raw_api.send_message(message.chat.id, "Select the advertisement category:", rows)
        return

    adwizard.WIZARD_PENDING[user_id] = pending
    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"adwiz:acct:{i}"}] for i, bot in enumerate(adbots)]
    rows.append([{"text": "Cancel", "callback_data": "myadbot:open"}])
    await raw_api.send_message(message.chat.id, "Which Ad Bot Account do you want to use?", rows)


@router.message(Command("manage"))
async def cmd_manage_shortcut(message: Message):
    user_id = message.from_user.id
    if not has_active_subscription(user_id):
        await message.reply("Your subscription has expired. Tap Buy Ad Bot to renew and get set up again.")
        return
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await message.reply("You don't have any Ad Bot Accounts yet.")
        return
    rows = []
    for i, bot in enumerate(adbots):
        rows.append([{"text": store.slot_display_name(bot, i), "callback_data": f"myad:manage_one:{i}"}])
    rows.append([{"text": "Back", "callback_data": "myadbot:open"}])
    await raw_api.send_message(message.chat.id, "<b>Manage Ad Bot</b>\n\nSelect an account:", rows)

@router.message(Command("live"))
async def cmd_live_shortcut(message: Message):
    user_id = message.from_user.id
    if not has_active_subscription(user_id):
        await message.reply("Your subscription has expired. Tap Buy Ad Bot to renew and get set up again.")
        return
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await message.reply("You don't have any Ad Bot Accounts yet.")
        return
    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"myad:live_one:{i}"}] for i, bot in enumerate(adbots)]
    rows.append([{"text": "Back", "callback_data": "myadbot:open"}])
    await raw_api.send_message(message.chat.id, "<b>Live Advertisement</b>\n\nSelect an account:", rows)

# Add a new line here whenever a new customer-facing command is added anywhere
# in the codebase, so /command always stays accurate.
CUSTOMER_COMMANDS = [
    ("/start", "Open your dashboard — manage your Ad Bot Accounts and subscription."),
    ("/ad", "Set your advertisement message link. Usage: /ad https://t.me/yourchannel/5"),
    ("/manage", "Manage one of your Ad Bot Accounts (rename, view, replace, etc.)."),
    ("/live", "See the current live advertisement running on one of your Ad Bot Accounts."),
    ("/logs", "See your advertisement posting logs from the last 15 minutes."),
    ("/mylists", "View and delete your custom marketplace collections."),
    ("/command", "Show this list of every command you have."),
]

@router.message(Command("command"))
async def cmd_list_commands(message: Message):
    """Shows the customer every command available to them."""
    import html as _html
    lines = ["<b>Your Commands</b>", ""]
    for cmd, desc in CUSTOMER_COMMANDS:
        lines.append(f"<code>{_html.escape(cmd)}</code>\n{_html.escape(desc)}\n")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "myadbot:prestock_skip_name")
async def cb_prestock_skip_name(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = EDIT_PENDING.get(user_id)
    if not pending or pending.get("step") != "await_prestock_name":
        await callback.answer("Session expired.", show_alert=True)
        return
    pending["name"] = None
    pending["step"] = "await_prestock_bio"
    EDIT_PENDING[user_id] = pending
    await raw_api.send_message(callback.message.chat.id, "Enter a bio to use for these accounts (optional).", [[{"text": "Skip", "callback_data": "myadbot:prestock_skip_bio"}]])
    await callback.answer()

@router.callback_query(F.data == "myadbot:prestock_skip_bio")
async def cb_prestock_skip_bio(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = EDIT_PENDING.get(user_id)
    if not pending or pending.get("step") != "await_prestock_bio":
        await callback.answer("Session expired.", show_alert=True)
        return
    pending["bio"] = None
    pending["step"] = "await_prestock_photo"
    EDIT_PENDING[user_id] = pending
    await raw_api.send_message(callback.message.chat.id, "Send a photo to use for these accounts (optional).", [[{"text": "Skip", "callback_data": "myadbot:prestock_skip_photo"}]])
    await callback.answer()

@router.callback_query(F.data == "myadbot:prestock_skip_photo")
async def cb_prestock_skip_photo(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = EDIT_PENDING.get(user_id)
    if not pending or pending.get("step") != "await_prestock_photo":
        await callback.answer("Session expired.", show_alert=True)
        return
    pending["photo_file_id"] = None
    store.set_prestock_profile(user_id, {"name": pending.get("name"), "bio": pending.get("bio"), "photo_file_id": None})
    EDIT_PENDING.pop(user_id, None)
    await callback.message.answer("Saved! Your remaining Ad Bot Account(s) will use this profile automatically once available.")
    await callback.answer()
