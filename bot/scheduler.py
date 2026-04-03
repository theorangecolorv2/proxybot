import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from yookassa import Payment
from yookassa.domain.exceptions.not_found_error import NotFoundError

from db import (
    get_expired_subscriptions, deactivate_subscription,
    get_all_active_subscriptions, was_notification_sent, mark_notification_sent,
    get_pending_payments, update_payment_status,
)
from proxy_manager import remove_secret
from handlers import CE_ZAP, CE_FIRE, CE_SUCCESS, _cover
from webhook import process_successful_payment

logger = logging.getLogger(__name__)

RENEW_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy_sub")],
])


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(cleanup_expired, "interval", minutes=5, args=[bot])
    scheduler.add_job(check_expiry_notifications, "interval", hours=1, args=[bot])
    scheduler.add_job(poll_pending_payments, "interval", seconds=15, args=[bot])
    return scheduler


async def cleanup_expired(bot: Bot):
    expired = await get_expired_subscriptions()
    for sub in expired:
        try:
            await remove_secret(sub["username"])
        except Exception:
            logger.exception("Failed to remove secret for %s", sub["username"])
        await deactivate_subscription(sub["id"])

        # Send "expired" notification if not sent yet
        if not await was_notification_sent(sub["id"], "expired"):
            await mark_notification_sent(sub["id"], "expired")
            try:
                await bot.send_photo(
                    sub["telegram_id"],
                    _cover(),
                    caption=(
                        f"{CE_ZAP} Ваша подписка закончилась\n\n"
                        f"Мы скучаем! Будем рады видеть вас снова {CE_FIRE}\n"
                        f"Продлите подписку, и всё заработает как прежде {CE_SUCCESS}"
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=RENEW_KB,
                )
            except Exception:
                logger.exception("Failed to notify user %s about expiry", sub["telegram_id"])


async def check_expiry_notifications(bot: Bot):
    subs = await get_all_active_subscriptions()
    now = datetime.now(timezone.utc)

    for sub in subs:
        expires = datetime.fromisoformat(sub["expires_at"])
        delta = expires - now
        total_seconds = delta.total_seconds()

        if total_seconds <= 0:
            continue  # Will be handled by cleanup_expired

        days_left = int(total_seconds // 86400)
        hours_left = total_seconds / 3600

        # Determine which notification to send
        notif_type = None
        text = None

        if days_left == 2:
            notif_type = "expiring_2days"
            text = (
                f"{CE_ZAP} Ваша подписка будет активна ещё два дня\n\n"
                f"Рекомендуем продлить подписку заранее, чтобы не потерять доступ к телеграм {CE_FIRE}"
            )
        elif days_left == 1:
            notif_type = "expiring_1day"
            text = (
                f"{CE_ZAP} Ваша подписка будет активна ещё сутки\n\n"
                f"Рекомендуем продлить подписку заранее, чтобы не потерять доступ к телеграм {CE_FIRE}"
            )
        elif days_left == 0 and 0 < hours_left <= 1:
            notif_type = "expiring_1hour"
            text = (
                f"{CE_ZAP} Ваша подписка будет активна ещё один час\n\n"
                f"Рекомендуем продлить подписку заранее, чтобы не потерять доступ к телеграм {CE_FIRE}"
            )

        if notif_type and not await was_notification_sent(sub["id"], notif_type):
            await mark_notification_sent(sub["id"], notif_type)
            try:
                await bot.send_photo(
                    sub["telegram_id"],
                    _cover(),
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=RENEW_KB,
                )
            except Exception:
                logger.exception("Failed to send %s notification for sub %s", notif_type, sub["id"])


async def poll_pending_payments(bot: Bot):
    pending = await get_pending_payments()
    for p in pending:
        try:
            yk_payment = await asyncio.wait_for(
                asyncio.to_thread(Payment.find_one, p["yookassa_payment_id"]),
                timeout=10,
            )
            if yk_payment.status == "succeeded":
                await process_successful_payment(bot, p["yookassa_payment_id"])
                logger.info("Polling: processed succeeded payment %s", p["yookassa_payment_id"])
            elif yk_payment.status == "canceled":
                await update_payment_status(p["yookassa_payment_id"], "canceled")
                logger.info("Polling: marked payment %s as canceled", p["yookassa_payment_id"])
        except NotFoundError:
            await update_payment_status(p["yookassa_payment_id"], "expired")
            logger.info("Polling: payment %s not found in YooKassa, marked expired", p["yookassa_payment_id"])
        except asyncio.TimeoutError:
            logger.warning("Polling: timeout checking payment %s", p["yookassa_payment_id"])
        except Exception:
            logger.exception("Polling: failed to check payment %s", p["yookassa_payment_id"])
