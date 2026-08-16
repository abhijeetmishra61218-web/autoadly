"""
AutoAdly - Shared Telegram profile update logic (name, bio, username, photo)
Used both when an account is auto-assigned (random defaults) and when a
customer manually edits it later via Manage Ad Bot.
"""

import asyncio
import random
import io
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest, CheckUsernameRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.errors import UsernameOccupiedError, UsernameInvalidError

RANDOM_NAME_WORDS = ["Nova", "Orbit", "Vertex", "Pulse", "Zenith", "Drift", "Ember", "Halo", "Quartz", "Blaze"]

def random_name():
    return random.choice(RANDOM_NAME_WORDS) + str(random.randint(100, 999))

async def update_name_bio(client, display_name, bio):
    """Sends the name/bio update, then VERIFIES it actually landed by re-fetching
       the account's live profile from Telegram before reporting success.

       This closes a real bug: on some accounts Telegram accepts an
       UpdateProfileRequest without raising an error, yet never actually applies
       it (observed on accounts under a soft/spam-related restriction that
       doesn't block posting). Without verification, the bot would tell the
       customer "Name updated" even though nothing changed. Now it re-checks the
       live profile (with one short retry, in case of propagation delay) and
       only reports success if the name/bio genuinely match."""
    bio = bio or ""
    try:
        await client(UpdateProfileRequest(first_name=display_name, last_name="@AutoAdlyAds", about=bio))
    except Exception as e:
        print(f"[profile_updater] name/bio update failed: {e}")
        return False

    for attempt in range(2):
        if attempt == 1:
            await asyncio.sleep(2)  # brief allowance for propagation before the final check
        try:
            me = await client.get_me()
            full = await client(GetFullUserRequest(me))
            actual_name = getattr(me, "first_name", None)
            actual_about = getattr(getattr(full, "full_user", None), "about", None) or ""
            if actual_name == display_name and actual_about == bio:
                return True
        except Exception as e:
            print(f"[profile_updater] name/bio verification failed: {e}")
            return False

    print(f"[profile_updater] name/bio update did not verify — Telegram accepted the request but the profile did not actually change (display_name={display_name!r}).")
    return False

import re

def _sanitize_username_base(raw):
    return re.sub(r"[^a-z0-9]", "", (raw or "").lower())

async def update_username(client, desired_username):
    base = _sanitize_username_base(desired_username) or _sanitize_username_base(random_name())
    attempt = 0
    while attempt <= 200:
        candidate = base if attempt == 0 else f"{base}{attempt}"
        candidate = candidate[:32]
        try:
            await client(CheckUsernameRequest(candidate))
            await client(UpdateUsernameRequest(candidate))
            return candidate
        except (UsernameOccupiedError, UsernameInvalidError):
            attempt += 1
    print(f"[profile_updater] Could not find an available username based on {base!r} after 200 attempts.")
    return None

async def update_photo(client, bot, photo_file_id):
    try:
        file = await bot.get_file(photo_file_id)
        photo_bytes = await bot.download_file(file.file_path)
        uploaded = await client.upload_file(io.BytesIO(photo_bytes.read()), file_name="profile.jpg")
        await client(UploadProfilePhotoRequest(file=uploaded))
        return True
    except Exception as e:
        print(f"[profile_updater] photo update failed: {e}")
        return False

async def update_photo_from_bytes(client, photo_bytes_io):
    """Like update_photo, but takes raw photo bytes directly (used when copying
       a photo from one Telegram account to another, not from a bot file_id)."""
    try:
        uploaded = await client.upload_file(photo_bytes_io, file_name="profile.jpg")
        await client(UploadProfilePhotoRequest(file=uploaded))
        return True
    except Exception as e:
        print(f"[profile_updater] photo-from-bytes update failed: {e}")
        return False

async def fetch_profile_from_username(client, username):
    """
    Fetch another Telegram user's public profile.

    Returns:
        {
            "name": str,
            "bio": str,
            "photo_bytes": bytes | None,
        }
    """
    username = (username or "").strip().lstrip("@")

    if not username:
        return None

    entity = await client.get_entity(username)
    full = await client(GetFullUserRequest(entity))

    user = getattr(full, "user", None) or entity
    full_user = getattr(full, "full_user", None)

    name = " ".join(
        value
        for value in (
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        )
        if value
    ).strip()

    if not name:
        name = "User"

    bio = ""
    if full_user is not None:
        bio = getattr(full_user, "about", None) or ""

    photo_bytes = None

    if getattr(user, "photo", None):
        try:
            photo_bytes = await client.download_profile_photo(
                user,
                file=bytes,
            )
        except Exception as e:
            print(
                f"[profile_updater] source photo download failed "
                f"username={username}: {e}"
            )

    return {
        "name": name[:64],
        "bio": bio[:70],
        "photo_bytes": photo_bytes,
    }

