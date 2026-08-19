# handlers.py
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import CommandStart, Command
import asyncio
import join_engine

import raw_api
import content_store as store
from config import OWNER_USERNAME

router = Router()

# in-memory pending-edit state per admin user_id: {user_id: {"action": "edit_welcome_text"}}
PENDING = {}

def _fmt_welcome(user):
    settings = store.load_settings()
    name = user.first_name or "there"
    return settings["welcome_text"].replace("{name}", name)

def _home_rows(user_id):
    settings = store.load_settings()
    emojis = store.load_action_emojis()
    labels = settings.get("button_labels", {})
    rows = [
        [{"text": labels.get("buy", "Buy Ad Bot"), "callback_data": "buy:plans", "emoji_id": emojis.get("buy_ad_bot_home")}],
        [
            {"text": labels.get("support", "Support"), "url": f"https://t.me/{OWNER_USERNAME}", "emoji_id": emojis.get("support")},
            {"text": labels.get("terms", "Terms & Conditions"), "callback_data": "open:terms", "emoji_id": emojis.get("terms")},
        ],
    ]
    import myadbot
    if myadbot.has_active_subscription(user_id):
        rows.insert(0, [{"text": "My Ad Bot", "callback_data": "myadbot:open", "emoji_id": emojis.get("myadbot_home")}])

    if store.is_admin(user_id):
        rows.append([
            {"text": "🖼 Set Welcome Photo", "callback_data": "admin:set_photo"},
            {"text": "⚙️ Edit Page", "callback_data": "admin:edit_menu"},
        ])
    return rows

def _plan_list_rows(user_id):
    emojis = store.load_action_emojis()
    rows = []
    for plan in store.load_plans():
        rows.append([{"text": f"{plan['name']} — {plan['price']}", "callback_data": f"plan:{plan['id']}", "emoji_id": plan.get("emoji_id")}])
    if store.is_admin(user_id):
        rows.append([{"text": "Edit Plans Page Photo", "callback_data": "plans_admin:set_photo"}])
        rows.append([{"text": "Edit Plans Page Text", "callback_data": "plans_admin:set_text"}])
    rows.append([{"text": "Back", "callback_data": "start:home", "emoji_id": emojis.get("back_button")}])
    return rows

def _plan_detail_rows(plan_id, user_id):
    emojis = store.load_action_emojis()
    rows = [
        [{"text": "Buy Now", "callback_data": f"buy:{plan_id}", "emoji_id": emojis.get("buy_now")}],
    ]
    if store.is_admin(user_id):
        rows.append([{"text": "Edit This Plan's Photo", "callback_data": f"plan_admin:setphoto:{plan_id}"}])
        rows.append([{"text": "Edit This Plan's Text", "callback_data": f"plan_admin:settext:{plan_id}"}])
        rows.append([{"text": "Edit This Plan's Emoji", "callback_data": f"plan_admin:setemoji:{plan_id}"}])
    rows.append([{"text": "Back", "callback_data": "buy:plans", "emoji_id": emojis.get("back_button")}])
    return rows

def _plan_detail_text(plan):
    if plan.get("custom_text"):
        return f"<b>{plan['custom_text']}</b>"
    benefits_lines = "\n".join(f"• {b}" for b in plan.get("benefits", []))
    body = (
        f"{plan['name']} Plan\n\n"
        f"Price : {plan['price']}\n\n"
        f"Benefits :\n{benefits_lines}"
    )
    return f"<b>{body}</b>"

def _edit_menu_rows():
    return [
        [{"text": "✏️ Edit Welcome Text", "callback_data": "admin:edit_welcome_text"}],
        [{"text": "🖼 Edit Welcome Photo", "callback_data": "admin:set_photo"}],
        [{"text": "🏷 Rename 'Buy Ad Bot' button", "callback_data": "admin:rename:buy"}],
        [{"text": "🏷 Rename 'Support' button", "callback_data": "admin:rename:support"}],
        [{"text": "🏷 Rename 'Terms' button", "callback_data": "admin:rename:terms"}],
        [{"text": "✏️ Edit Terms Text", "callback_data": "admin:edit_terms_text"}],
        [{"text": "Set Emoji: Buy Ad Bot (home)", "callback_data": "admin:setemoji:buy_ad_bot_home"}],
        [{"text": "Set Emoji: Buy Now button", "callback_data": "admin:setemoji:buy_now"}],
        [{"text": "Set Emoji: Support button", "callback_data": "admin:setemoji:support"}],
        [{"text": "Set Emoji: Terms button", "callback_data": "admin:setemoji:terms"}],
        [{"text": "Set Emoji: Back button", "callback_data": "admin:setemoji:back_button"}],
        [{"text": "Set Emoji: Back to Home button", "callback_data": "admin:setemoji:back_to_home_button"}],
        [{"text": "Set Emoji: My Ad Bot (home)", "callback_data": "admin:setemoji:myadbot_home"}],
        [{"text": "Set Emoji: Set Advertisement", "callback_data": "admin:setemoji:dash_set_ad"}],
        [{"text": "Set Emoji: Advertisement Logs", "callback_data": "admin:setemoji:dash_logs"}],
        [{"text": "Set Emoji: Live Advertisement", "callback_data": "admin:setemoji:dash_live"}],
        [{"text": "Set Emoji: Manage Ad Bot", "callback_data": "admin:setemoji:dash_manage"}],
        [{"text": "Set Emoji: Subscription", "callback_data": "admin:setemoji:dash_subscription"}],
        [{"text": "Set Emoji: Category buttons (per button)", "callback_data": "admin:cat_emoji_menu"}],
        [{"text": "Set Emoji: Marketplace list buttons (per button)", "callback_data": "admin:list_emoji_menu"}],
        [{"text": "Back", "callback_data": "start:home"}],
    ]

@router.message(CommandStart())
async def cmd_start(message: Message):
    store.register_user(message.from_user.id, message.from_user.username)
    store.ensure_owner(message.from_user.id)  # first-ever /start becomes owner
    settings = store.load_settings()
    await raw_api.send_message(
        message.chat.id,
        _fmt_welcome(message.from_user),
        _home_rows(message.from_user.id),
        photo=settings.get("welcome_image"),
    )

@router.message(Command("cofounder"))
async def cmd_cofounder(message: Message):
    if not store.is_admin(message.from_user.id):
        await message.reply("Only the owner or an existing co-founder can use this command.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await message.reply("Usage: /cofounder @username")
        return
    target_uid = store.get_uid_by_username(parts[1])
    if not target_uid:
        await message.reply("That user hasn't started the bot yet. Ask them to send /start first, then try again.")
        return
    store.add_cofounder(target_uid)
    await message.reply(f"{parts[1]} is now a co-founder with full edit access.")

@router.message(F.text.regexp(r"^/getemojiid"))
async def cmd_getemojiid(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    if not message.entities:
        await message.reply(
            "No custom emoji found. Send /getemojiid followed directly by the custom emoji itself, "
            "in the same message (e.g. type /getemojiid then paste the emoji right after it)."
        )
        return
    found = []
    for ent in message.entities:
        if ent.type == "custom_emoji":
            char = message.text[ent.offset: ent.offset + ent.length]
            found.append(f"{char}  ->  {ent.custom_emoji_id}")
    if found:
        await message.reply("\n".join(found))
    else:
        await message.reply("No custom emoji entities found in that message — make sure it's an actual custom/premium emoji, not a regular one.")


@router.callback_query(F.data == "start:home")
async def cb_home(callback: CallbackQuery):
    settings = store.load_settings()
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        _fmt_welcome(callback.from_user), _home_rows(callback.from_user.id),
        photo=settings.get("welcome_image"),
    )
    await callback.answer()

@router.callback_query(F.data == "buy:plans")
async def cb_show_plans(callback: CallbackQuery):
    settings = store.load_settings()
    text = settings.get("plans_page_text", "Choose a plan:")
    photo = settings.get("plans_page_image")
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        text, _plan_list_rows(callback.from_user.id), photo=photo,
    )
    await callback.answer()

@router.callback_query(F.data.startswith("plan:"))
async def cb_plan_detail(callback: CallbackQuery):
    plan_id = callback.data.split(":", 1)[1]
    plan = store.get_plan(plan_id)
    if not plan:
        await callback.answer("Plan not found.", show_alert=True)
        return
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        _plan_detail_text(plan), _plan_detail_rows(plan_id, callback.from_user.id), photo=plan.get("image"),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("buy:"))
async def cb_buy_now(callback: CallbackQuery):
    plan_id = callback.data.split(":", 1)[1]
    if plan_id == "plans":
        return
    plan = store.get_plan(plan_id)
    if not plan:
        await callback.answer("Plan not found.", show_alert=True)
        return
    import payments_flow
    await payments_flow.start_payment(callback, plan)

@router.callback_query(F.data == "open:terms")
async def cb_terms(callback: CallbackQuery):
    settings = store.load_settings()
    rows = []
    if store.is_admin(callback.from_user.id):
        rows.append([{"text": "Edit Terms & Conditions", "callback_data": "admin:edit_terms_text"}])
    rows.append([{"text": "Back", "callback_data": "start:home"}])
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        settings["terms_text"], rows,
    )
    await callback.answer()

# ---------- ADMIN EDIT PANEL ----------

@router.callback_query(F.data == "admin:edit_menu")
async def cb_admin_edit_menu(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        "Owner Edit Panel — choose what to edit:", _edit_menu_rows(),
    )
    await callback.answer()

@router.callback_query(F.data == "admin:set_photo")
async def cb_admin_set_photo(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    PENDING[callback.from_user.id] = {"action": "set_welcome_photo"}
    await callback.message.answer("Send the new welcome photo now (or send 0 to remove the current image).")
    await callback.answer()

@router.callback_query(F.data == "admin:edit_welcome_text")
async def cb_admin_edit_welcome_text(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    PENDING[callback.from_user.id] = {"action": "edit_welcome_text"}
    await callback.message.answer(
        "Send the new welcome text. You can use {name} anywhere you want the customer's first name inserted, and basic HTML like <b>bold</b>."
    )
    await callback.answer()

@router.callback_query(F.data == "admin:edit_terms_text")
async def cb_admin_edit_terms_text(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    PENDING[callback.from_user.id] = {"action": "edit_terms_text"}
    await callback.message.answer("Send the new Terms & Conditions text.")
    await callback.answer()

@router.callback_query(F.data.startswith("admin:rename:"))
async def cb_admin_rename_button(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    key = callback.data.split(":", 2)[2]  # buy / support / terms
    PENDING[callback.from_user.id] = {"action": "rename_button", "key": key}
    await callback.message.answer(f"Send the new label for the '{key}' button:")
    await callback.answer()

@router.message(F.text, ~F.text.startswith("/"), F.from_user.id.in_(PENDING.keys()))
async def on_admin_text(message: Message):
    print(f"[DEBUG] on_admin_text caught message from {message.from_user.id}: {message.text[:50]!r}")
    pending = PENDING.get(message.from_user.id)
    if not pending or not store.is_admin(message.from_user.id):
        return

    action = pending["action"]
    if action == "awaiting_marketplace_batch":
        identifiers = message.text.split()
        PENDING.pop(message.from_user.id, None)
        await _start_join_batch(message, identifiers)
        return
    if action == "edit_welcome_text":
        s = store.load_settings()
        s["welcome_text"] = message.text
        store.save_settings(s)
        await message.reply("Welcome text updated.")
    elif action == "edit_terms_text":
        s = store.load_settings()
        s["terms_text"] = message.text
        store.save_settings(s)
        await message.reply("Terms text updated.")
    elif action == "rename_button":
        store.set_button_label(pending["key"], message.text)
        await message.reply(f"Button renamed to \'{message.text}\'.")
    elif action == "set_welcome_photo" and message.text.strip() == "0":
        s = store.load_settings()
        s["welcome_image"] = None
        store.save_settings(s)
        await message.reply("Welcome photo removed.")
    elif action == "set_category_emoji":
        val = message.text.strip()
        emoji_id = None if val == "0" else int(val)
        store.set_category_emoji(pending["category"], emoji_id)
        await message.reply("Category emoji updated." if emoji_id else "Category emoji removed.")
    elif action == "set_list_emoji":
        val = message.text.strip()
        emoji_id = None if val == "0" else int(val)
        store.set_list_emoji(pending["list_name"], emoji_id)
        await message.reply("List button emoji updated." if emoji_id else "List button emoji removed.")
    elif action == "set_button_emoji":
        val = message.text.strip()
        emoji_id = None if val == "0" else int(val)
        store.set_action_emoji(pending["key"], emoji_id)
        await message.reply("Button emoji updated." if emoji_id else "Button emoji removed.")
    elif action == "set_page_text":
        target = pending["target"]
        if target == "plans_list":
            s = store.load_settings()
            s["plans_page_text"] = message.text
            store.save_settings(s)
            await message.reply("Plans page text updated.")
        elif message.text.strip() == "0":
            store.update_plan(target, custom_text=None)
            await message.reply("Plan text reset to default layout.")
        else:
            store.update_plan(target, custom_text=message.text)
            await message.reply("Plan text updated.")
    elif action == "set_plan_emoji":
        val = message.text.strip()
        emoji_id = None if val == "0" else int(val)
        store.update_plan(pending["target"], emoji_id=emoji_id)
        await message.reply("Plan emoji updated." if emoji_id else "Plan emoji removed.")
    elif action == "set_page_photo" and message.text.strip() == "0":
        target = pending["target"]
        if target == "plans_list":
            s = store.load_settings()
            s["plans_page_image"] = None
            store.save_settings(s)
        else:
            store.update_plan(target, image=None)
        await message.reply("Photo removed.")

    PENDING.pop(message.from_user.id, None)

@router.message(F.photo, F.from_user.id.in_(PENDING.keys()))
async def on_admin_photo(message: Message):
    pending = PENDING.get(message.from_user.id)
    if not pending or not store.is_admin(message.from_user.id):
        return
    action = pending["action"]
    file_id = message.photo[-1].file_id

    if action == "set_welcome_photo":
        s = store.load_settings()
        s["welcome_image"] = file_id
        store.save_settings(s)
        await message.reply("Welcome photo updated.")
    elif action == "set_page_photo":
        target = pending["target"]
        if target == "plans_list":
            s = store.load_settings()
            s["plans_page_image"] = file_id
            store.save_settings(s)
            await message.reply("Plans page photo updated.")
        else:
            store.update_plan(target, image=file_id)
            await message.reply("Plan photo updated.")
    else:
        return

    PENDING.pop(message.from_user.id, None)

@router.callback_query(F.data.startswith("admin:setemoji:"))
async def cb_admin_set_emoji(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    key = callback.data.split(":", 2)[2]
    PENDING[callback.from_user.id] = {"action": "set_button_emoji", "key": key}
    await callback.message.answer(
        f"Send the custom emoji's document_id for '{key}' (use /getemojiid to get one), or send 0 to remove it."
    )
    await callback.answer()


@router.callback_query(F.data == "plans_admin:set_photo")
async def cb_plans_admin_set_photo(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    PENDING[callback.from_user.id] = {"action": "set_page_photo", "target": "plans_list"}
    await callback.message.answer("Send the new photo for the Plans page (or send 0 to remove it).")
    await callback.answer()

@router.callback_query(F.data == "plans_admin:set_text")
async def cb_plans_admin_set_text(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    PENDING[callback.from_user.id] = {"action": "set_page_text", "target": "plans_list"}
    await callback.message.answer("Send the new text for the Plans page.")
    await callback.answer()

@router.callback_query(F.data.startswith("plan_admin:setphoto:"))
async def cb_plan_admin_set_photo(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    plan_id = callback.data.split(":", 2)[2]
    PENDING[callback.from_user.id] = {"action": "set_page_photo", "target": plan_id}
    await callback.message.answer("Send the new photo for this plan (or send 0 to remove it).")
    await callback.answer()

@router.callback_query(F.data.startswith("plan_admin:settext:"))
async def cb_plan_admin_set_text(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    plan_id = callback.data.split(":", 2)[2]
    PENDING[callback.from_user.id] = {"action": "set_page_text", "target": plan_id}
    await callback.message.answer("Send the new text for this plan (replaces the auto-generated benefits list). Send 0 to reset to the default layout.")
    await callback.answer()


@router.callback_query(F.data.startswith("plan_admin:setemoji:"))
async def cb_plan_admin_set_emoji(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    plan_id = callback.data.split(":", 2)[2]
    PENDING[callback.from_user.id] = {"action": "set_plan_emoji", "target": plan_id}
    await callback.message.answer("Send the custom emoji's document_id for this plan's button (use /getemojiid), or send 0 to remove it.")
    await callback.answer()


@router.message(Command("addg"))
async def cmd_addg(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    PENDING[message.from_user.id] = {"action": "awaiting_marketplace_batch"}
    await message.reply(
        "Send the marketplace usernames or links now, separated by spaces.\n"
        "Example: @group1 @group2 https://t.me/group3"
    )

@router.message(Command("add"))
async def cmd_add(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    parts = message.text.split()[1:]
    if not parts:
        await message.reply("Usage: /add @m1 @m2 https://t.me/m3 ...")
        return
    await _start_join_batch(message, parts)

async def _start_join_batch(message: Message, identifiers):
    await message.reply(f"Joining {len(identifiers)} marketplace(s) across all ad accounts in the background. You will get a summary when done.")

    async def progress(text):
        await message.answer(text)

    asyncio.create_task(join_engine.run_join_batch(identifiers, progress_callback=progress))


@router.callback_query(F.data == "admin:cat_emoji_menu")
async def cb_admin_cat_emoji_menu(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    import adwizard
    rows = [[{"text": cat, "callback_data": f"admin:setcatEmoji:{cat}"}] for cat in adwizard.CATEGORIES]
    rows.append([{"text": "Back", "callback_data": "admin:edit_menu"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "Pick a category to set its emoji:", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("admin:setcatEmoji:"))
async def cb_admin_set_cat_emoji(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    category = callback.data.split(":", 2)[2]
    PENDING[callback.from_user.id] = {"action": "set_category_emoji", "category": category}
    await callback.message.answer(f"Send the emoji document_id for '{category}' (use /getemojiid), or send 0 to remove it.")
    await callback.answer()

@router.callback_query(F.data == "admin:list_emoji_menu")
async def cb_admin_list_emoji_menu(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    import database as db
    presets = await db.get_preset_lists()
    rows = [[{"text": p["name"], "callback_data": f"admin:setlistEmoji:{p['name']}"}] for p in presets]
    rows.append([{"text": "Add Custom Marketplaces (button)", "callback_data": "admin:setlistEmoji:Add Custom Marketplaces"}])
    rows.append([{"text": "Back", "callback_data": "admin:edit_menu"}])
    await raw_api.render(callback.message.chat.id, callback.message.message_id, "Pick a marketplace list button to set its emoji:", rows)
    await callback.answer()

@router.callback_query(F.data.startswith("admin:setlistEmoji:"))
async def cb_admin_set_list_emoji(callback: CallbackQuery):
    if not store.is_admin(callback.from_user.id):
        await callback.answer("Admins only.", show_alert=True)
        return
    list_name = callback.data.split(":", 2)[2]
    PENDING[callback.from_user.id] = {"action": "set_list_emoji", "list_name": list_name}
    await callback.message.answer(f"Send the emoji document_id for '{list_name}' (use /getemojiid), or send 0 to remove it.")
    await callback.answer()
