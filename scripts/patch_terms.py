import re

with open("handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''@router.callback_query(F.data == "open:terms")
async def cb_terms(callback: CallbackQuery):
    settings = store.load_settings()
    await raw_api.render(
        callback.message.chat.id, callback.message.message_id,
        settings["terms_text"], [[{"text": "Back", "callback_data": "start:home"}]],
    )
    await callback.answer()'''

new = '''@router.callback_query(F.data == "open:terms")
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
    await callback.answer()'''

if old not in content:
    print("PATCH FAILED: could not find the exact cb_terms function to replace.")
else:
    content = content.replace(old, new)
    with open("handlers.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Patch applied successfully.")
