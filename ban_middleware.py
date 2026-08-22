"""
AutoAdly - Blocks banned users from interacting with the bot at all, everywhere.
"""

from aiogram import BaseMiddleware
import content_store as store

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.username:
            # Keep the username cache fresh on every interaction, not just /start —
            # previously only /start refreshed it, so any customer who renamed their
            # Telegram username after their last /start would have every admin
            # lookup (/view, /change, /alog, /alive, /force, etc.) silently target
            # a stale, no-longer-valid username. Only refresh when a username is
            # actually present on this event, so we never blank out a known-good
            # cached username due to some update type not carrying it.
            store.register_user(user.id, user.username)
        if user and store.is_banned(user.id):
            if hasattr(event, "answer"):
                try:
                    await event.answer("You are banned from using this bot.")
                except Exception:
                    pass
            return
        return await handler(event, data)
