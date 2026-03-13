from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from urllib.parse import quote

from config import PROXY_HOST, PROXY_PORT, PROXY_PRICE
from db import add_user, get_active_subscriptions, create_payment
from secret_gen import make_tls_link_secret
from payment import create_yookassa_payment

router = Router()

CE_ZAP = '<tg-emoji emoji-id="5219943216781995020">⚡</tg-emoji>'
CE_CONNECT = '<tg-emoji emoji-id="5454386656628991407">🔗</tg-emoji>'


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить прокси", callback_data="buy_proxy")],
        [InlineKeyboardButton(text="Мои прокси", callback_data="my_proxies")],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    await add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"{CE_ZAP} <b>MTProxy для Telegram</b>\n\n"
        f"Быстрый и надёжный прокси.\n"
        f"Подключение в один клик, подписка на 30 дней.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


@router.callback_query(F.data == "buy_proxy")
async def buy_proxy(callback: CallbackQuery):
    telegram_id = callback.from_user.id

    try:
        result = create_yookassa_payment(telegram_id)
    except Exception:
        await callback.message.answer(
            "Ошибка при создании платежа. Попробуйте позже.",
            reply_markup=main_keyboard(),
        )
        await callback.answer()
        return

    await create_payment(telegram_id, result["payment_id"], PROXY_PRICE)

    await callback.message.answer(
        f"<b>Подписка на 30 дней</b> — {PROXY_PRICE} ₽\n\n"
        f"После оплаты прокси будет создан автоматически.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=result["confirmation_url"])],
            [InlineKeyboardButton(text="← Назад", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.answer(
        f"{CE_ZAP} <b>MTProxy для Telegram</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "my_proxies")
async def my_proxies(callback: CallbackQuery):
    subs = await get_active_subscriptions(callback.from_user.id)

    if not subs:
        await callback.message.answer(
            "У вас пока нет активных подписок.",
            reply_markup=main_keyboard(),
        )
        await callback.answer()
        return

    lines = []
    for i, sub in enumerate(subs, 1):
        link_secret = make_tls_link_secret(sub["secret"])
        link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
        expires = sub["expires_at"][:10]
        lines.append(f"{CE_CONNECT} Прокси #{i} — до {expires}\n{link}")

    await callback.message.answer(
        f"<b>Ваши прокси:</b>\n\n" + "\n\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    await callback.answer()
