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
)
from secret_gen import generate_raw_secret, make_tls_link_secret
from proxy_manager import add_secret
from handlers import main_keyboard, CE_SUCCESS, CE_LINK

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

        await update_payment_status(payment_id, "succeeded")

        telegram_id = payment["telegram_id"]
        devices = payment.get("devices", 1)
        months = payment.get("months", 1)
        bot: Bot = request.app["bot"]

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

    elif event_type == "payment.canceled":
        await update_payment_status(payment_id, "canceled")

    return web.Response(status=200)


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
