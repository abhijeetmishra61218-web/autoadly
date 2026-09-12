"""
AutoAdly - Requires users to join @AutoAdlyAds before using the bot.
"""
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

CHANNEL_USERNAME = "@AutoAdlyAds"

class JoinCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        bot = data.get("bot")

        if not user or not bot:
            return await handler(event, data)

        try:
            member = await bot.get_chat_member(CHANNEL_USERNAME, user.id)
            is_member = member.status in ("member", "administrator", "creator")
        except Exception as e:
            print(f"[join_check] failed to verify membership for {user.id}: {e}")
            is_member = False

        if not is_member:
            text = (
                f"To use this bot, please join {CHANNEL_USERNAME} first.\n\n"
                "After joining, send /start again to continue."
            )
            rows = [[{"text": "Join Channel", "url": f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"}]]
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer("Please join the channel first.", show_alert=True)
                    await event.message.answer(text, reply_markup=_inline_kb(rows))
                elif isinstance(event, Message):
                    await event.answer(text, reply_markup=_inline_kb(rows))
            except Exception as e:
                print(f"[join_check] failed to notify {user.id}: {e}")
            return

        return await handler(event, data)


def _inline_kb(rows):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb_rows = [[InlineKeyboardButton(text=b["text"], url=b.get("url")) for b in row] for row in rows]
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)
