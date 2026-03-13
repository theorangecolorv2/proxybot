import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from db import get_expired_subscriptions, deactivate_subscription
from proxy_manager import remove_secret

logger = logging.getLogger(__name__)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_expired, "interval", minutes=5, args=[bot])
    return scheduler


async def cleanup_expired(bot: Bot):
    expired = await get_expired_subscriptions()
    for sub in expired:
        try:
            await remove_secret(sub["username"])
        except Exception:
            logger.exception("Failed to remove secret for %s", sub["username"])
        await deactivate_subscription(sub["id"])
        try:
            await bot.send_message(
                sub["telegram_id"],
                "Ваша подписка на прокси истекла. Нажмите /start чтобы приобрести новую.",
            )
        except Exception:
            logger.exception("Failed to notify user %s", sub["telegram_id"])
