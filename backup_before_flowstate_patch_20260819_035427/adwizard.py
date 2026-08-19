"""
AutoAdly - Set Advertisement wizard
"""

import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import raw_api
import content_store as store
import database as db
import engine

router = Router()

WIZARD_PENDING = {}

CATEGORIES = ["Telegram", "Discord", "Instagram", "Facebook", "WhatsApp", "TikTok", "X (Twitter)", "YouTube", "Exchange", "Others"]

def _parse_ad_link(raw_link):
    """Returns (username_or_none, internal_id_or_none, message_id) or None if unparseable."""
    raw_link = raw_link.strip()
    m = re.search(r"t\.me/c/(\d+)/(\d+)", raw_link)
    if m:
        return None, int(m.group(1)), int(m.group(2))
    m = re.search(r"t\.me/([A-Za-z0-9_]+)/(\d+)", raw_link)
    if m:
        return m.group(1), None, int(m.group(2))
    return None

async def _resolve_source_chat(client, username, internal_id):
    from telethon import utils
    from telethon.tl.types import PeerChannel
    if internal_id is not None:
        entity = await client.get_entity(PeerChannel(internal_id))
    else:
        entity = await client.get_entity(username)
    return utils.get_peer_id(entity)

@router.callback_query(F.data == "myad:set_ad")
async def cb_set_ad_start(callback: CallbackQuery):
    user_id = callback.from_user.id
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await callback.answer("You don't have an Ad Bot Account yet.", show_alert=True)
        return
    WIZARD_PENDING[user_id] = {"step": "await_link"}
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        "Send the advertisement message link.\n\nExample: https://t.me/yourchannel/123",
        [[{"text": "Cancel", "callback_data": "myadbot:open"}]],
    )
    await callback.answer()

@router.message(Command("set"))
async def cmd_set_ad_start(message: Message):
    user_id = message.from_user.id
    adbots = store.get_customer_adbots(user_id)
    if not adbots:
        await message.reply("You don't have an Ad Bot Account yet.")
        return
    WIZARD_PENDING[user_id] = {"step": "await_link"}
    await raw_api.send_message(
        message.chat.id,
        "Send the advertisement message link.\n\nExample: https://t.me/yourchannel/123",
        [[{"text": "Cancel", "callback_data": "myadbot:open"}]],
    )

@router.message(F.text, ~F.text.startswith("/"), F.from_user.id.in_(WIZARD_PENDING.keys()))
async def on_wizard_text(message: Message):
    user_id = message.from_user.id
    pending = WIZARD_PENDING.get(user_id)
    if not pending:
        return
    step = pending["step"]

    if step == "await_link":
        parsed = _parse_ad_link(message.text)
        if not parsed:
            await message.reply("That doesn't look like a valid Telegram message link. Example: https://t.me/yourchannel/123")
            return
        username, internal_id, msg_id = parsed
        pending.update({"username": username, "internal_id": internal_id, "msg_id": msg_id})

        if pending.get("ad_account_id"):
            # Account was already pre-selected (e.g. via "Change Ad" on Live Advertisement) — skip straight to category
            pending["step"] = "choose_category"
            WIZARD_PENDING[user_id] = pending
            rows = []
            row = []
            for cat in CATEGORIES:
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

        pending["step"] = "choose_account"
        WIZARD_PENDING[user_id] = pending
        await _show_account_picker(message.chat.id, None, user_id)

    elif step == "await_folder_link":
        folder_link = message.text.strip()
        wait = await message.reply("Joining the groups/forums from that folder with your Ad Bot Account, this may take a minute...")
        import join_engine
        ad_account_id = pending["ad_account_id"]
        list_id = await db.get_or_create_list(f"pending_custom_{user_id}", category="All", owner_customer_id=user_id)
        try:
            await join_engine.run_join_batch_single_account(ad_account_id, [folder_link], list_id)
        except AttributeError:
            await wait.edit_text("Custom marketplace joining isn't fully wired up yet — contact support.")
            return
        pending.update({"step": "await_custom_name", "custom_list_id": list_id})
        WIZARD_PENDING[user_id] = pending
        try:
            await wait.edit_text("Joined! Now enter a name for this marketplace collection.\n\nExample: My Crypto Groups")
        except Exception:
            await message.reply("Joined! Now enter a name for this marketplace collection.\n\nExample: My Crypto Groups")

    elif step == "await_custom_name":
        name = message.text.strip()
        await db.save_list_name(pending["custom_list_id"], name)
        await _activate_ad(message.chat.id, None, user_id, pending, pending["custom_list_id"])

    elif step == "await_private_invite_link":
        invite_link = message.text.strip()
        wait = await message.reply("Joining the private channel with your Ad Bot Account, please wait...")
        import join_engine
        ad_account_id = pending["ad_account_id"]
        client = await engine.get_client(ad_account_id)
        entity = await join_engine.join_one(client, invite_link)
        if not entity:
            await wait.edit_text("Could not join that channel — check the invite link is correct and still valid, then send it again.")
            return
        try:
            await wait.edit_text("Joined! Setting up your advertisement now...")
        except Exception:
            pass
        list_id = pending.get("list_id")
        await _activate_ad(message.chat.id, None, user_id, pending, list_id)

async def _show_account_picker(chat_id, msg_id, user_id):
    adbots = store.get_customer_adbots(user_id)
    rows = [[{"text": store.slot_display_name(bot, i), "callback_data": f"adwiz:acct:{i}"}] for i, bot in enumerate(adbots)]
    rows.append([{"text": "Cancel", "callback_data": "myadbot:open"}])
    text = "Which Ad Bot Account do you want to use?"
    if msg_id:
        await raw_api.render(chat_id, msg_id, text, rows)
    else:
        await raw_api.send_message(chat_id, text, rows)

@router.callback_query(F.data.startswith("adwiz:acct:"))
async def cb_pick_account(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = WIZARD_PENDING.get(user_id)
    if not pending:
        await callback.answer("Session expired.", show_alert=True)
        return
    idx = int(callback.data.split(":", 2)[2])
    adbots = store.get_customer_adbots(user_id)
    if idx >= len(adbots):
        await callback.answer("Not found.", show_alert=True)
        return
    bot = adbots[idx]
    pending["ad_account_id"] = bot["ad_account_id"]
    pending["ad_bot_name"] = bot["name"]

    existing = await db.get_active_ad_for_account(bot["ad_account_id"])
    if existing:
        pending["step"] = "confirm_replace"
        pending["existing_ad_id"] = existing["id"]
        WIZARD_PENDING[user_id] = pending
        await raw_api.render(
            callback.message.chat.id, callback.message.message_id,
            f"<b>{bot['name']}</b> already has an active advertisement running (category: {existing['category']}).\n\nDo you want to replace it with the new one?",
            [
                [{"text": "Confirm", "callback_data": "adwiz:confirm_replace"}],
                [{"text": "Cancel", "callback_data": "myadbot:open"}],
            ],
        )
        await callback.answer()
        return

    pending["step"] = "choose_category"
    WIZARD_PENDING[user_id] = pending
    await _show_category_picker(callback)

@router.callback_query(F.data == "adwiz:confirm_replace")
async def cb_confirm_replace(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = WIZARD_PENDING.get(user_id)
    if not pending:
        await callback.answer("Session expired.", show_alert=True)
        return
    pending["step"] = "choose_category"
    WIZARD_PENDING[user_id] = pending
    await _show_category_picker(callback)

async def _show_category_picker(callback):
    rows = []
    row = []
    for cat in CATEGORIES:
        btn = {"text": cat, "callback_data": f"adwiz:cat:{cat}"}
        emoji_id = store.get_category_emoji(cat)
        if emoji_id:
            btn["emoji_id"] = emoji_id
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "Cancel", "callback_data": "myadbot:open"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "Select the advertisement category:", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("adwiz:cat:"))
async def cb_pick_category(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = WIZARD_PENDING.get(user_id)
    if not pending:
        await callback.answer("Session expired.", show_alert=True)
        return
    category = callback.data.split(":", 2)[2]
    pending["category"] = category
    pending["step"] = "choose_list"
    WIZARD_PENDING[user_id] = pending
    await _show_list_picker(callback, user_id)

async def _show_list_picker(callback, user_id):
    presets = await db.get_preset_lists()
    custom_lists = await db.get_customer_custom_lists(user_id)
    rows = []
    for p in presets:
        emoji_id = store.get_list_emoji(p["name"])
        rows.append([{"text": p["name"], "callback_data": f"adwiz:list:{p['id']}", "emoji_id": emoji_id}])
    for cl in custom_lists:
        if cl["name"].startswith("pending_custom_"):
            continue
        emoji_id = store.get_list_emoji(cl["name"])
        rows.append([{"text": cl["name"], "callback_data": f"adwiz:list:{cl['id']}", "emoji_id": emoji_id}])
    add_custom_emoji = store.get_list_emoji("Add Custom Marketplaces")
    rows.append([{"text": "Add Custom Marketplaces", "callback_data": "adwiz:list:custom", "emoji_id": add_custom_emoji}])
    rows.append([{"text": "Cancel", "callback_data": "myadbot:open"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "Select the marketplace list for your advertisement.", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("adwiz:list:"))
async def cb_pick_list(callback: CallbackQuery):
    user_id = callback.from_user.id
    pending = WIZARD_PENDING.get(user_id)
    if not pending:
        await callback.answer("Session expired.", show_alert=True)
        return
    choice = callback.data.split(":", 2)[2]

    if choice == "custom":
        pending["step"] = "await_folder_link"
        WIZARD_PENDING[user_id] = pending
        await raw_api.render(
            callback.message.chat.id, callback.message.message_id,
            "Send a folder link containing Telegram group/forum links (e.g. https://t.me/addlist/...).",
            [[{"text": "Cancel", "callback_data": "myadbot:open"}]],
        )
        await callback.answer()
        return

    list_id = int(choice)
    try:
        await _activate_ad(callback.message.chat.id, callback.message.message_id, user_id, pending, list_id)
    finally:
        await callback.answer()

async def _activate_ad(chat_id, msg_id, user_id, pending, list_id):
    ad_account_id = pending["ad_account_id"]
    try:
        client = await engine.get_client(ad_account_id)
    except ValueError:
        text = (
            "Your Ad Bot Account is no longer available (it may have just been replaced or removed).\n\n"
            "Please start over from the dashboard."
        )
        rows = [[{"text": "Back to Dashboard", "callback_data": "myadbot:open"}]]
        if msg_id:
            await raw_api.render(chat_id, msg_id, text, rows)
        else:
            await raw_api.send_message(chat_id, text, rows)
        WIZARD_PENDING.pop(user_id, None)
        return
    try:
        source_chat_id = await _resolve_source_chat(client, pending.get("username"), pending.get("internal_id"))
    except Exception as e:
        is_private_link = pending.get("internal_id") is not None
        already_asked = pending.get("step") == "await_private_invite_link"
        if is_private_link and not already_asked:
            pending["step"] = "await_private_invite_link"
            pending["list_id"] = list_id
            WIZARD_PENDING[user_id] = pending
            text = (
                "This looks like a private channel your Ad Bot Account isn't a member of yet.\n\n"
                "Please send the channel's invite link (e.g. https://t.me/+AbCdEf or https://t.me/joinchat/AbCdEf) "
                "so we can join it and access your advertisement."
            )
            rows = [[{"text": "Cancel", "callback_data": "myadbot:open"}]]
            if msg_id:
                await raw_api.render(chat_id, msg_id, text, rows)
            else:
                await raw_api.send_message(chat_id, text, rows)
            return

        text = f"Could not access that advertisement message with your Ad Bot Account: {e}\n\nMake sure the account is a member of that chat, or the link is public."
        if msg_id:
            await raw_api.render(chat_id, msg_id, text, [[{"text": "Back", "callback_data": "myadbot:open"}]])
        else:
            await raw_api.send_message(chat_id, text, [[{"text": "Back", "callback_data": "myadbot:open"}]])
        WIZARD_PENDING.pop(user_id, None)
        return

    existing_ad_id = pending.get("existing_ad_id")
    if existing_ad_id:
        await db.stop_advertisement(existing_ad_id)

    await db.create_advertisement(ad_account_id, source_chat_id, pending["msg_id"], pending["category"], list_id, source_username=pending.get("username"))
    WIZARD_PENDING.pop(user_id, None)

    text = f"Your advertisement is now live on <b>{pending['ad_bot_name']}</b>!\n\nCategory: {pending['category']}\n\nIt will begin posting shortly."
    rows = [[{"text": "Back to Dashboard", "callback_data": "myadbot:open"}]]
    if msg_id:
        await raw_api.render(chat_id, msg_id, text, rows)
    else:
        await raw_api.send_message(chat_id, text, rows)
