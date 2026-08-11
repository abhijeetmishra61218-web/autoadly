with open("handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

old_menu = '''def _edit_menu_rows():
    return [
        [{"text": "✏️ Edit Welcome Text", "callback_data": "admin:edit_welcome_text"}],
        [{"text": "🖼 Edit Welcome Photo", "callback_data": "admin:set_photo"}],
        [{"text": "🏷 Rename 'Buy Ad Bot' button", "callback_data": "admin:rename:buy"}],
        [{"text": "🏷 Rename 'Support' button", "callback_data": "admin:rename:support"}],
        [{"text": "🏷 Rename 'Terms' button", "callback_data": "admin:rename:terms"}],
        [{"text": "✏️ Edit Terms Text", "callback_data": "admin:edit_terms_text"}],
        [{"text": "Back", "callback_data": "start:home"}],
    ]'''

new_menu = '''def _edit_menu_rows():
    return [
        [{"text": "✏️ Edit Welcome Text", "callback_data": "admin:edit_welcome_text"}],
        [{"text": "🖼 Edit Welcome Photo", "callback_data": "admin:set_photo"}],
        [{"text": "🏷 Rename 'Buy Ad Bot' button", "callback_data": "admin:rename:buy"}],
        [{"text": "🏷 Rename 'Support' button", "callback_data": "admin:rename:support"}],
        [{"text": "🏷 Rename 'Terms' button", "callback_data": "admin:rename:terms"}],
        [{"text": "✏️ Edit Terms Text", "callback_data": "admin:edit_terms_text"}],
        [{"text": "Set Emoji: Buy button", "callback_data": "admin:setemoji:buy_now"}],
        [{"text": "Set Emoji: Support button", "callback_data": "admin:setemoji:support"}],
        [{"text": "Set Emoji: Terms button", "callback_data": "admin:setemoji:terms"}],
        [{"text": "Set Emoji: Back button", "callback_data": "admin:setemoji:back_button"}],
        [{"text": "Back", "callback_data": "start:home"}],
    ]'''

assert old_menu in content, "Still no match — paste 'sed -n 65,75p handlers.py' again"
content = content.replace(old_menu, new_menu)

addition = '''

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
'''
content = content + addition

old_dispatch = '''    elif action == "set_welcome_photo" and message.text.strip() == "0":
        s = store.load_settings()
        s["welcome_image"] = None
        store.save_settings(s)
        await message.reply("Welcome photo removed.")'''

new_dispatch = '''    elif action == "set_welcome_photo" and message.text.strip() == "0":
        s = store.load_settings()
        s["welcome_image"] = None
        store.save_settings(s)
        await message.reply("Welcome photo removed.")
    elif action == "set_button_emoji":
        val = message.text.strip()
        emoji_id = None if val == "0" else int(val)
        store.set_action_emoji(pending["key"], emoji_id)
        await message.reply("Button emoji updated." if emoji_id else "Button emoji removed.")'''

assert old_dispatch in content, "Could not find on_admin_text dispatch to patch"
content = content.replace(old_dispatch, new_dispatch)

with open("handlers.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Emoji patch applied.")
