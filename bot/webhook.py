import json
import logging
from aiohttp import web
from aiogram import Bot
from aiogram.enums import ParseMode
from urllib.parse import quote

from config import YOOKASSA_WEBHOOK_PORT, PROXY_HOST, PROXY_PORT
from db import (
    get_payment_by_yookassa_id,
    update_payment_status,
    add_subscription,
    get_active_subscription,
    extend_subscription,
    get_referrer,
    has_referral_rewarded,
    mark_referral_rewarded,
)
from secret_gen import generate_raw_secret, make_tls_link_secret
from proxy_manager import add_secret, update_secret_ips
from handlers import main_keyboard, CE_SUCCESS, CE_LINK, CE_EARN, CE_FIRE

logger = logging.getLogger(__name__)


async def handle_yookassa_webhook(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.Response(status=400)

    event_type = body.get("event")
    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id")

    if not payment_id:
        return web.Response(status=400)

    if event_type == "payment.succeeded":
        payment = await get_payment_by_yookassa_id(payment_id)
        if not payment:
            logger.warning("Payment %s not found in DB", payment_id)
            return web.Response(status=200)

        if payment["status"] == "succeeded":
            return web.Response(status=200)

        telegram_id = payment["telegram_id"]
        devices = payment.get("devices", 1)
        months = payment.get("months", 1)
        bot: Bot = request.app["bot"]

        existing_sub = await get_active_subscription(telegram_id)

        if existing_sub:
            # Extend existing subscription — same secret, same link
            old_devices = existing_sub.get("devices", 1)
            if devices > old_devices:
                await update_secret_ips(existing_sub["username"], existing_sub["secret"], devices)
            await extend_subscription(existing_sub["id"], months=months, devices=devices)
            await update_payment_status(payment_id, "succeeded")

            link_secret = make_tls_link_secret(existing_sub["secret"])
            link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
            await bot.send_message(
                telegram_id,
                f"Оплата успешно прошла! Подписка продлена {CE_SUCCESS}\n\n"
                f"Ваша ссылка не изменилась {CE_LINK}\n\n"
                f"{link}",
                parse_mode=ParseMode.HTML,
                reply_markup=await main_keyboard(telegram_id),
            )
        else:
            # New subscription — create proxy secret
            raw_secret = generate_raw_secret()
            username = f"tg_{telegram_id}_{raw_secret[:8]}"

            success = await add_secret(username, raw_secret, max_unique_ips=devices)
            if not success:
                logger.error("Failed to create proxy for user %s", telegram_id)
                await bot.send_message(
                    telegram_id,
                    "Оплата прошла, но произошла ошибка при создании прокси. Обратитесь в поддержку.",
                )
                return web.Response(status=200)

            await update_payment_status(payment_id, "succeeded")

            link_secret = make_tls_link_secret(raw_secret)
            await add_subscription(telegram_id, raw_secret, username, devices=devices, months=months)

            link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
            await bot.send_message(
                telegram_id,
                f"Оплата успешно прошла! {CE_SUCCESS}\n\n"
                f"Нажмите на ссылку, далее нажмите подключиться и телеграмм летает! {CE_LINK}\n\n"
                f"{link}",
                parse_mode=ParseMode.HTML,
                reply_markup=await main_keyboard(telegram_id),
            )

        # --- Referral bonus ---
        await _process_referral_bonus(bot, telegram_id)

    elif event_type == "payment.canceled":
        await update_payment_status(payment_id, "canceled")

    return web.Response(status=200)


async def _process_referral_bonus(bot: Bot, telegram_id: int):
    referrer_id = await get_referrer(telegram_id)
    if not referrer_id:
        return
    if await has_referral_rewarded(telegram_id):
        return

    # Bonus for invited user — +5 days to their subscription
    inv_sub = await get_active_subscription(telegram_id)
    if inv_sub:
        await extend_subscription(inv_sub["id"], days=5)
        try:
            await bot.send_message(
                telegram_id,
                f"{CE_EARN} <b>Реферальный бонус!</b>\n\n"
                f"Вы получили <b>+5 дней</b> к подписке за регистрацию по приглашению! {CE_FIRE}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.error("Failed to notify invited user %s about referral bonus", telegram_id)

    # Bonus for referrer — +10 days to their subscription
    ref_sub = await get_active_subscription(referrer_id)
    if ref_sub:
        await extend_subscription(ref_sub["id"], days=10)
    else:
        # No active subscription — create a new one with 10 bonus days
        raw_ref = generate_raw_secret()
        uname_ref = f"tg_{referrer_id}_{raw_ref[:8]}"
        ok_ref = await add_secret(uname_ref, raw_ref, max_unique_ips=1)
        if not ok_ref:
            logger.error("Failed to create referral proxy for referrer %s", referrer_id)
            await mark_referral_rewarded(telegram_id)
            return
        await add_subscription(referrer_id, raw_ref, uname_ref, devices=1, months=0)
        # add_subscription creates with 0 months (0 days), now extend by 10 days
        new_sub = await get_active_subscription(referrer_id)
        if new_sub:
            await extend_subscription(new_sub["id"], days=10)

    try:
        await bot.send_message(
            referrer_id,
            f"{CE_EARN} <b>Реферальный бонус!</b>\n\n"
            f"Ваш друг оплатил подписку — вы получили <b>+10 дней</b> к подписке! {CE_FIRE}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.error("Failed to notify referrer %s about referral bonus", referrer_id)

    await mark_referral_rewarded(telegram_id)


async def start_webhook_server(bot: Bot) -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/yookassa/webhook", handle_yookassa_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", YOOKASSA_WEBHOOK_PORT)
    await site.start()
    logger.info("YooKassa webhook server started on port %s", YOOKASSA_WEBHOOK_PORT)
    return runner
