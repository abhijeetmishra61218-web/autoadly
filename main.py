import asyncio
import signal
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import router
import payments_admin
import payments_flow
import myadbot
import adwizard
import admin_commands
import ban_middleware
import join_middleware
import account_setup
import backup_system
import restriction_monitor
import github_backup
import subscription_expiry
import engine

import fcntl
import sys

_lock_file = open("/tmp/autoadly_bot.lock", "w")
try:
    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("Another instance of the bot is already running. Exiting.")
    sys.exit(1)

async def main():
    print("[main] booting", flush=True)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.outer_middleware(ban_middleware.BanMiddleware())
    dp.callback_query.outer_middleware(ban_middleware.BanMiddleware())
    dp.message.outer_middleware(join_middleware.JoinCheckMiddleware())
    dp.callback_query.outer_middleware(join_middleware.JoinCheckMiddleware())
    dp.include_router(router)
    dp.include_router(payments_admin.router)
    dp.include_router(payments_flow.router)
    dp.include_router(myadbot.router)
    dp.include_router(adwizard.router)
    dp.include_router(admin_commands.router)
    dp.include_router(account_setup.router)
    dp.include_router(restriction_monitor.router)

    asyncio.create_task(backup_system.cleanup_loop())
    asyncio.create_task(github_backup.backup_loop())
    asyncio.create_task(subscription_expiry.expiry_loop())
    asyncio.create_task(restriction_monitor.daily_recheck_loop())
    asyncio.create_task(engine.start_engine())
    asyncio.create_task(account_setup.resume_unsynced_joins())

    shutdown_event = asyncio.Event()

    def _on_shutdown_signal():
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_shutdown_signal)
    print("[main] signal handlers registered", flush=True)

    async def _shutdown_watcher():
        print("[main] shutdown watcher task started, awaiting event", flush=True)
        await shutdown_event.wait()
        print("[main] Shutdown signal received - sending best-effort ad_bot.db backup before exit...", flush=True)
        try:
            import backup_system as _bs
            await _bs.send_db_backup(triggered_by="shutdown (auto)")
        except Exception as e:
            print(f"[main] Shutdown backup failed: {e}", flush=True)
        await dp.stop_polling()

    asyncio.create_task(_shutdown_watcher())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
