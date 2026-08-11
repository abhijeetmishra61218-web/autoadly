import re

with open("handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

def replace_func(content, name, new_body):
    pattern = re.compile(
        rf"(?ms)^def {re.escape(name)}\(.*?(?=^def |^@router\.|\Z)"
    )
    matches = list(pattern.finditer(content))
    if len(matches) != 1:
        print(f"  [{name}] found {len(matches)} matches — skipping (expected exactly 1)")
        return content
    content = content[:matches[0].start()] + new_body + content[matches[0].end():]
    print(f"  [{name}] replaced OK")
    return content

new_plan_list_rows = '''def _plan_list_rows(user_id):
    emojis = store.load_action_emojis()
    rows = []
    for plan in store.load_plans():
        rows.append([{"text": f"{plan['name']} \u2014 {plan['price']}", "callback_data": f"plan:{plan['id']}"}])
    if store.is_admin(user_id):
        rows.append([{"text": "Edit Plans Page Photo", "callback_data": "plans_admin:set_photo"}])
        rows.append([{"text": "Edit Plans Page Text", "callback_data": "plans_admin:set_text"}])
    rows.append([{"text": "Back", "callback_data": "start:home", "emoji_id": emojis.get("back_button")}])
    return rows

'''

new_plan_detail_rows = '''def _plan_detail_rows(plan_id, user_id):
    emojis = store.load_action_emojis()
    rows = [
        [{"text": "Buy Now", "callback_data": f"buy:{plan_id}", "emoji_id": emojis.get("buy_now")}],
    ]
    if store.is_admin(user_id):
        rows.append([{"text": "Edit This Plan's Photo", "callback_data": f"plan_admin:setphoto:{plan_id}"}])
        rows.append([{"text": "Edit This Plan's Text", "callback_data": f"plan_admin:settext:{plan_id}"}])
    rows.append([{"text": "Back", "callback_data": "buy:plans", "emoji_id": emojis.get("back_button")}])
    return rows

'''

new_plan_detail_text = '''def _plan_detail_text(plan):
    if plan.get("custom_text"):
        return f"<b>{plan['custom_text']}</b>"
    benefits_lines = "\\n".join(f"\u2022 {b}" for b in plan.get("benefits", []))
    body = (
        f"{plan['name']} Plan\\n\\n"
        f"Price : {plan['price']}\\n\\n"
        f"Benefits :\\n{benefits_lines}"
    )
    return f"<b>{body}</b>"

'''

new_cb_show_plans = '''def _cb_show_plans_placeholder():
    pass

'''

content = replace_func(content, "_plan_list_rows", new_plan_list_rows)
content = replace_func(content, "_plan_detail_rows", new_plan_detail_rows)
content = replace_func(content, "_plan_detail_text", new_plan_detail_text)

# cb_show_plans and cb_plan_detail need their bodies updated to pass user_id / use new settings keys.
# These are handled via targeted substring replacement since they're short and stable.

old_show_plans = 'async def cb_show_plans(callback: CallbackQuery):\n    await raw_api.render(\n        callback.message.chat.id, callback.message.message_id,\n        "Choose a plan:", _plan_list_rows(callback.from_user.id),\n    )\n    await callback.answer()'
new_show_plans = '''async def cb_show_plans(callback: CallbackQuery):
    settings = store.load_settings()
    text = settings.get("plans_page_text", "Choose a plan:")
    photo = settings.get("plans_page_image")
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        text, _plan_list_rows(callback.from_user.id), photo=photo,
    )
    await callback.answer()'''

if old_show_plans in content:
    content = content.replace(old_show_plans, new_show_plans)
    print("  [cb_show_plans] replaced OK")
else:
    print("  [cb_show_plans] exact text not found — will need manual check")

old_plan_detail_call = '_plan_detail_text(plan), _plan_detail_rows(plan_id), photo=plan.get("image"),'
new_plan_detail_call = '_plan_detail_text(plan), _plan_detail_rows(plan_id, callback.from_user.id), photo=plan.get("image"),'
if old_plan_detail_call in content:
    content = content.replace(old_plan_detail_call, new_plan_detail_call)
    print("  [cb_plan_detail call] updated OK")
else:
    print("  [cb_plan_detail call] exact text not found — will need manual check")

# Append new admin callback handlers for plans-page and per-plan editing
new_handlers = '''

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
'''
content += new_handlers
print("  [new admin callback handlers] appended")

with open("handlers.py", "w", encoding="utf-8") as f:
    f.write(content)
