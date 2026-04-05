import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from db import init_db
from handlers import router
from admin import router as admin_router
from scheduler import setup_scheduler
from webhook import start_webhook_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

HEALTH_FILE = "/tmp/health"
WATCHDOG_INTERVAL = 30  # seconds between checks
WATCHDOG_MAX_FAILURES = 3  # consecutive failures before exit


async def health_watchdog(bot: Bot):
    """Periodically pings Telegram API; exits process if unreachable."""
    failures = 0
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL)
        try:
            await asyncio.wait_for(bot.get_me(), timeout=10)
            failures = 0
            with open(HEALTH_FILE, "w") as f:
                f.write("ok")
        except Exception:
            failures += 1
            logger.warning("Watchdog: Telegram API unreachable (%d/%d)", failures, WATCHDOG_MAX_FAILURES)
            if failures >= WATCHDOG_MAX_FAILURES:
                logger.error("Watchdog: %d consecutive failures, terminating for restart", failures)
                sys.exit(1)


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    webhook_runner = await start_webhook_server(bot)

    asyncio.create_task(health_watchdog(bot))

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await webhook_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
