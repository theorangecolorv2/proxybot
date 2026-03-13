import asyncio
import logging
from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from db import init_db
from handlers import router
from scheduler import setup_scheduler
from webhook import start_webhook_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    webhook_runner = await start_webhook_server(bot)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await webhook_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
