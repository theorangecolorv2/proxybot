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

logger = logging.getLogger(__name__)


def main_keyboard():
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить прокси", callback_data="buy_proxy")],
        [InlineKeyboardButton(text="Мои прокси", callback_data="my_proxies")],
    ])


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
        bot: Bot = request.app["bot"]

        raw_secret = generate_raw_secret()
        username = f"tg_{telegram_id}_{raw_secret[:8]}"

        success = await add_secret(username, raw_secret)
        if not success:
            logger.error("Failed to create proxy for user %s", telegram_id)
            await bot.send_message(
                telegram_id,
                "Оплата прошла, но произошла ошибка при создании прокси. Обратитесь в поддержку.",
            )
            return web.Response(status=200)

        link_secret = make_tls_link_secret(raw_secret)
        await add_subscription(telegram_id, raw_secret, username)

        CE_CONNECT = '<tg-emoji emoji-id="5454386656628991407">🔗</tg-emoji>'

        link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
        await bot.send_message(
            telegram_id,
            f"<b>Оплата прошла!</b>\n\n"
            f"{CE_CONNECT} Нажмите для подключения:\n{link}\n\n"
            f"Подписка активна на 30 дней.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
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
