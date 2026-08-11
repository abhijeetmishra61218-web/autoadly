with open("myadbot.py") as f:
    src = f.read()

# Let's find the actual copy_profile function and patch it properly
import re

# Find the copy_profile function
pattern = r'(async def copy_profile\(callback: types\.CallbackQuery, user_id: int, idx: int\):.*?)(?=\n    |\n\n|$)'
match = re.search(pattern, src, re.DOTALL)
if not match:
    print("copy_profile function not found")
    exit(1)

old_func = match.group(1)

# New function implementation
new_func = '''async def copy_profile(callback: types.CallbackQuery, user_id: int, idx: int):
    """Copy user's profile to ad bot"""
    bot = adbots[idx]
    tg_user = callback.from_user
    display_name = f"{tg_user.first_name or 'User'} #{idx + 1}"
    bio = ""
    is_assigned = bot.get("ad_account_id") is not None

    file_id = None
    try:
        bot_api = Bot(token=config.BOT_TOKEN)
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
        await callback.answer("Profile copied to your Ad Bot Account.", show_alert=True)
    else:
        # If assigned, use the old method or handle differently
        client = await engine.get_client(bot["ad_account_id"])
        ok_name = await pu.update_name_bio(client, display_name, bio)
        photo_ok = False
        if file_id:
            try:
                bot_api = Bot(token=config.BOT_TOKEN)
                photo_ok = await pu.update_photo(client, bot_api, file_id)
                await bot_api.session.close()
            except Exception as e:
                print(f"[copy_profile] photo copy failed: {e}")
        await callback.answer("Profile copied to your Ad Bot Account." if ok_name else "Copy partially failed, please try again.", show_alert=True)'''

# Replace the function
src = src.replace(old_func, new_func)

# Write the updated file
with open("myadbot.py", "w") as f:
    f.write(src)

print("Patch applied successfully!")
