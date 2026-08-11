with open("myadbot.py") as f:
    src = f.read()

old1 = '''    if assigned:
        rows.append([{"text": "Copy Your Profile", "callback_data": f"myad:copyprofile:{idx}"}])
    rows.append([{"text": "Back", "callback_data": "myad:manage"}])'''
new1 = '''    rows.append([{"text": "Copy Your Profile", "callback_data": f"myad:copyprofile:{idx}"}])
    rows.append([{"text": "Back", "callback_data": "myad:manage"}])'''
assert old1 in src, "block 1 not found"
src = src.replace(old1, new1)

old2 = '''    bot = adbots[idx]
    tg_user = callback.from_user
    display_name = f"{tg_user.first_name or 'User'} #{idx + 1}"
    bio = ""
    client = await engine.get_client(bot["ad_account_id"])
    ok_name = await pu.update_name_bio(client, display_name, bio)
    photo_ok = False
    try:
        bot_api = Bot(token=config.BOT_TOKEN)
        user_photos = await bot_api.get_user_profile_photos(user_id, limit=1)
        if user_photos.total_count > 0:
            file_id = user_photos.photos[0][-1].file_id
            photo_ok = await pu.update_photo(client, bot_api, file_id)
        await bot_api.session.close()
    except Exception as e:
        print(f"[copy_profile] photo copy failed: {e}")
    await callback.answer("Profile copied to your Ad Bot Account." if ok_name else "Copy partially failed, please try again.", show_alert=True)'''
new2 = '''    bot = adbots[idx]
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
        try:
            await bot_api.session.close()
        except Exception:
            pass
        await callback.answer("Profile saved — it will be applied automatically once an Ad Bot Account is assigned.", show_alert=True)
        return

    client = await engine.get_client(bot["ad_account_id"])
    ok_name = await pu.update_name_bio(client, display_name, bio)
    photo_ok = False
    if file_id:
        try:
            photo_ok = await pu.update_photo(client, bot_api, file_id)
        except Exception as e:
            print(f"[copy_profile] photo copy failed: {e}")
    try:
        await bot_api.session.close()
    except Exception:
        pass
    await callback.answer("Profile copied to your Ad Bot Account." if ok_name else "Copy partially failed, please try again.", show_alert=True)'''
assert old2 in src, "block 2 not found"
src = src.replace(old2, new2)

with open("myadbot.py", "w") as f:
    f.write(src)
print("patched OK")
