"""
AutoAdly - Blocks banned users from interacting with the bot at all, everywhere.
"""

from aiogram import BaseMiddleware
import content_store as store

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and store.is_banned(user.id):
            if hasattr(event, "answer"):
                try:
                    await event.answer("You are banned from using this bot.")
                except Exception:
                    pass
            return
        return await handler(event, data)
