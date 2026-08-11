with open("handlers.py", "r", encoding="utf-8") as f:
    content = f.read()

anchor = '@router.callback_query(F.data == "start:home")'
assert anchor in content, "Could not find anchor point to insert /getemojiid command"

addition = '''@router.message(F.text.regexp(r"^/getemojiid"))
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
        await message.reply("\\n".join(found))
    else:
        await message.reply("No custom emoji entities found in that message — make sure it's an actual custom/premium emoji, not a regular one.")


''' + anchor

content = content.replace(anchor, addition, 1)

with open("handlers.py", "w", encoding="utf-8") as f:
    f.write(content)
print("getemojiid command added.")
