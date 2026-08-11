with open("handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

imports_old = "from aiogram.filters import CommandStart, Command"
imports_new = "from aiogram.filters import CommandStart, Command\nimport asyncio\nimport join_engine"
assert imports_old in content
content = content.replace(imports_old, imports_new, 1)

addition = '''

@router.message(Command("addg"))
async def cmd_addg(message: Message):
    if not store.is_admin(message.from_user.id):
        return
    PENDING[message.from_user.id] = {"action": "awaiting_marketplace_batch"}
    await message.reply(
        "Send the marketplace usernames or links now, separated by spaces.\\n"
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
    await message.reply(f"Joining {len(identifiers)} marketplace(s) across all ad accounts in the background. You'll get a summary when it's done.")

    async def progress(text):
        await message.answer(text)

    asyncio.create_task(join_engine.run_join_batch(identifiers, progress_callback=progress))
'''
content += addition

old_dispatch_marker = '    elif action == "set_button_emoji":'
new_case = '''    elif action == "awaiting_marketplace_batch":
        identifiers = message.text.split()
        await _start_join_batch(message, identifiers)
'''
assert old_dispatch_marker in content
content = content.replace(old_dispatch_marker, new_case + "    elif action == \"set_button_emoji\":", 1)

with open("handlers.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Marketplace commands patch applied.")
