from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto
from aiogram.enums import ParseMode
from urllib.parse import quote
import os

from config import PROXY_HOST, PROXY_PORT
from db import (
    add_user, get_active_subscriptions, create_payment,
    has_used_trial, mark_trial_used, add_subscription,
    set_referrer, get_referral_count,
)
from secret_gen import generate_raw_secret, make_tls_link_secret
from proxy_manager import add_secret
from payment import create_yookassa_payment
from pricing import get_device_price, get_discount, calculate_total

router = Router()

# --- Premium custom emoji helpers ---

def ce(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

CE_ZAP = ce("5219943216781995020", "⚡")
CE_CONNECT = ce("5454386656628991407", "🔗")
CE_CART = ce("5346267284518239633", "🛒")
CE_SUB = ce("5346092874486281349", "⚡")
CE_SUCCESS = ce("5980930633298350051", "✅")
CE_LINK = ce("5271604874419647061", "🔗")
CE_DEVICES = ce("5819062970998590994", "📱")
CE_DURATION = ce("5346220920346277355", "⏳")
CE_PRICE = ce("5246762912428603768", "📉")
CE_DISCOUNT = ce("5406683434124859552", "🏷")
CE_TOTAL = ce("5231449120635370684", "💸")
CE_EARN = ce("5283232570660634549", "💰")
CE_PHONE = ce("5453965363286925977", "📞")
CE_HEART = ce("5454249887690415056", "❤️")
CE_FIRE = ce("5222148368955877900", "🔥")


COVER_PHOTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover.png")


def _cover():
    return FSInputFile(COVER_PHOTO)


def _cover_media(text: str) -> InputMediaPhoto:
    return InputMediaPhoto(media=_cover(), caption=text, parse_mode=ParseMode.HTML)


class BuyFlow(StatesGroup):
    choosing_devices = State()
    entering_custom_devices = State()
    choosing_duration = State()
    entering_custom_duration = State()


async def main_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    rows = []

    trial_used = await has_used_trial(telegram_id)
    if not trial_used:
        rows.append([InlineKeyboardButton(
            text="Пробный период",
            callback_data="trial",
            icon_custom_emoji_id="5222148368955877900",  # 🔥
        )])

    subs = await get_active_subscriptions(telegram_id)
    buy_text = "Продлить подписку" if subs else "Купить прокси"
    rows.append([InlineKeyboardButton(
        text=buy_text,
        callback_data="buy_sub",
        icon_custom_emoji_id="5258024802010026053",  # 🛒
    )])
    rows.append([InlineKeyboardButton(
        text="Моя подписка",
        callback_data="my_proxies",
        icon_custom_emoji_id="5219943216781995020",  # ⚡
    )])
    rows.append([
        InlineKeyboardButton(
            text="Поддержка",
            url="https://t.me/ClevVPN_support",
            icon_custom_emoji_id="5453965363286925977",  # 📞
        ),
        InlineKeyboardButton(
            text="Реферальная",
            callback_data="referral",
            icon_custom_emoji_id="5283232570660634549",  # 💰
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def devices_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 устройство", callback_data="dev_1"),
            InlineKeyboardButton(text="3 устройства", callback_data="dev_3"),
        ],
        [
            InlineKeyboardButton(text="5 устройств", callback_data="dev_5"),
            InlineKeyboardButton(text="10 устройств", callback_data="dev_10"),
        ],
        [InlineKeyboardButton(text="Своё количество устройств", callback_data="dev_custom")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_menu")],
    ])


def duration_keyboard(devices: int) -> InlineKeyboardMarkup:
    def fmt(months: int) -> str:
        total = calculate_total(devices, months)
        discount = get_discount(months)
        label = f"{months} мес — {total}₽"
        if discount > 0:
            label += f" (-{discount}%)"
        return label

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=fmt(1), callback_data="dur_1"),
            InlineKeyboardButton(text=fmt(3), callback_data="dur_3"),
        ],
        [
            InlineKeyboardButton(text=fmt(6), callback_data="dur_6"),
            InlineKeyboardButton(text=fmt(12), callback_data="dur_12"),
        ],
        [InlineKeyboardButton(text="Своё количество месяцев", callback_data="dur_custom")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_devices")],
    ])




# --- /start ---

@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await add_user(uid, message.from_user.username)

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
            if referrer_id != uid:
                await set_referrer(uid, referrer_id)
        except ValueError:
            pass

    text = (
        f"{CE_ZAP} <b>ClevVPN — Прокси для Telegram</b>\n\n"
        f"С нами телеграмм всегда доступен! {CE_FIRE}"
    )
    await message.answer_photo(
        _cover(),
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=await main_keyboard(uid),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await add_user(uid, message.from_user.username)
    text = (
        f"{CE_ZAP} <b>ClevVPN — Прокси для Telegram</b>\n\n"
        f"С нами телеграмм всегда доступен! {CE_FIRE}"
    )
    await message.answer_photo(
        _cover(),
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=await main_keyboard(uid),
    )


# --- Trial period ---

@router.callback_query(F.data == "trial")
async def trial_period(callback: CallbackQuery):
    uid = callback.from_user.id
    used = await has_used_trial(uid)
    if used:
        await callback.answer("Вы уже использовали пробный период.", show_alert=True)
        return

    raw_secret = generate_raw_secret()
    username = f"tg_trial_{uid}_{raw_secret[:8]}"

    success = await add_secret(username, raw_secret, max_unique_ips=1)
    if not success:
        await callback.answer("Ошибка при создании прокси. Попробуйте позже.", show_alert=True)
        return

    link_secret = make_tls_link_secret(raw_secret)

    # Trial = 3 days, stored as 0 months — use special add
    from db import add_trial_subscription
    await add_trial_subscription(uid, raw_secret, username)
    await mark_trial_used(uid)

    link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
    await callback.message.edit_media(
        _cover_media(
            f"Вы успешно оформили пробный период на 3 дня! {CE_SUCCESS}\n\n"
            f"Нажмите на ссылку и нажмите подключиться, всё! Telegram летает {CE_LINK}\n\n"
            f"{link}"
        ),
        reply_markup=await main_keyboard(uid),
    )
    await callback.answer()


# --- Referral (placeholder) ---

@router.callback_query(F.data == "referral")
async def referral_info(callback: CallbackQuery):
    uid = callback.from_user.id
    bot_me = await callback.bot.me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{uid}"
    count = await get_referral_count(uid)

    text = (
        f"{CE_EARN} <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей и получай бесплатный прокси! {CE_FIRE}\n\n"
        f"{CE_LINK} <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"{CE_HEART} Приглашено друзей: <b>{count}</b>\n\n"
        f"{CE_ZAP} <b>Бонусы:</b>\n"
        f"— Друг получает <b>5 дней</b> бесплатного прокси\n"
        f"— Ты получаешь <b>10 дней</b> бесплатного прокси"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_menu")],
    ])

    await callback.message.edit_media(
        _cover_media(text),
        reply_markup=kb,
    )
    await callback.answer()


# --- Step 1: Choose devices ---

@router.callback_query(F.data == "buy_sub")
async def buy_sub(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.choosing_devices)
    await callback.message.edit_media(
        _cover_media("Выберите количество устройств:"),
        reply_markup=devices_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dev_"), BuyFlow.choosing_devices)
async def pick_device_count(callback: CallbackQuery, state: FSMContext):
    count_str = callback.data.split("_")[1]
    if count_str == "custom":
        await state.set_state(BuyFlow.entering_custom_devices)
        await callback.message.edit_media(
            _cover_media("Введите количество устройств (от 1 до 100):"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back_to_devices")],
            ]),
        )
        await callback.answer()
        return

    devices = int(count_str)
    await state.update_data(devices=devices)
    await state.set_state(BuyFlow.choosing_duration)
    await callback.message.edit_media(
        _cover_media(f"Устройств: {devices}\nВыберите срок подписки:"),
        reply_markup=duration_keyboard(devices),
    )
    await callback.answer()


@router.message(BuyFlow.entering_custom_devices)
async def enter_custom_devices(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or not (1 <= int(text) <= 100):
        await message.answer_photo(
            _cover(),
            caption="Введите число от 1 до 100:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back_to_devices")],
            ]),
        )
        return

    devices = int(text)
    await state.update_data(devices=devices)
    await state.set_state(BuyFlow.choosing_duration)
    await message.answer_photo(
        _cover(),
        caption=f"Устройств: {devices}\nВыберите срок подписки:",
        parse_mode=ParseMode.HTML,
        reply_markup=duration_keyboard(devices),
    )


# --- Step 2: Choose duration ---

@router.callback_query(F.data.startswith("dur_"), BuyFlow.choosing_duration)
async def pick_duration(callback: CallbackQuery, state: FSMContext):
    dur_str = callback.data.split("_")[1]
    if dur_str == "custom":
        await state.set_state(BuyFlow.entering_custom_duration)
        await callback.message.edit_media(
            _cover_media("Введите количество месяцев (от 1 до 36):"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back_to_duration")],
            ]),
        )
        await callback.answer()
        return

    months = int(dur_str)
    data = await state.get_data()
    devices = data["devices"]
    await state.update_data(months=months)
    await show_confirmation(callback.message, state, devices, months, edit=True)
    await callback.answer()


@router.message(BuyFlow.entering_custom_duration)
async def enter_custom_duration(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or not (1 <= int(text) <= 36):
        await message.answer_photo(
            _cover(),
            caption="Введите число от 1 до 36:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back_to_duration")],
            ]),
        )
        return

    months = int(text)
    data = await state.get_data()
    devices = data["devices"]
    await state.update_data(months=months)
    await show_confirmation(message, state, devices, months, edit=False)


async def show_confirmation(msg, state: FSMContext, devices: int, months: int, edit: bool = True):
    total = calculate_total(devices, months)
    discount = get_discount(months)
    price_per_month = get_device_price(devices)

    telegram_id = msg.chat.id if hasattr(msg, 'chat') else msg.from_user.id

    try:
        result = create_yookassa_payment(telegram_id, devices, months)
    except Exception:
        kb = await main_keyboard(telegram_id)
        if edit:
            await msg.edit_media(_cover_media("Ошибка при создании платежа. Попробуйте позже."), reply_markup=kb)
        else:
            await msg.answer_photo(_cover(), caption="Ошибка при создании платежа. Попробуйте позже.", parse_mode=ParseMode.HTML, reply_markup=kb)
        await state.clear()
        return

    await create_payment(telegram_id, result["payment_id"], result["amount"], devices, months)
    await state.clear()

    text = (
        f"<b>Ваш заказ:</b>\n\n"
        f"{CE_DEVICES} Устройств: {devices}\n\n"
        f"{CE_DURATION} Срок: {months} мес.\n\n"
        f"{CE_PRICE} Цена за месяц: {price_per_month}₽\n\n"
    )
    if discount > 0:
        text += f"{CE_DISCOUNT} Скидка: {discount}%\n\n"
    text += f"<b>Итого: {total}</b> {CE_TOTAL}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", url=result["confirmation_url"])],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_menu")],
    ])

    if edit:
        await msg.edit_media(_cover_media(text), reply_markup=kb)
    else:
        await msg.answer_photo(_cover(), caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)


# --- Back buttons ---

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = callback.from_user.id
    await callback.message.edit_media(
        _cover_media(
            f"{CE_ZAP} <b>ClevVPN — Прокси для Telegram</b>\n\n"
            f"С нами телеграмм всегда доступен! {CE_FIRE}"
        ),
        reply_markup=await main_keyboard(uid),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_devices")
async def back_to_devices(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.choosing_devices)
    await callback.message.edit_media(
        _cover_media("Выберите количество устройств:"),
        reply_markup=devices_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_duration")
async def back_to_duration(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    devices = data.get("devices", 1)
    await state.set_state(BuyFlow.choosing_duration)
    await callback.message.edit_media(
        _cover_media(f"Устройств: {devices}\nВыберите срок подписки:"),
        reply_markup=duration_keyboard(devices),
    )
    await callback.answer()


# --- My proxies ---

@router.callback_query(F.data == "my_proxies")
async def my_proxies(callback: CallbackQuery):
    uid = callback.from_user.id
    subs = await get_active_subscriptions(uid)

    proxies_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Продлить подписку",
            callback_data="buy_sub",
            icon_custom_emoji_id="5258024802010026053",  # 🛒
        )],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_menu")],
    ])

    if not subs:
        await callback.message.edit_media(
            _cover_media("У вас пока нет активных подписок."),
            reply_markup=proxies_kb,
        )
        await callback.answer()
        return

    # Show the latest-expiring subscription
    sub = max(subs, key=lambda s: s["expires_at"])
    link_secret = make_tls_link_secret(sub["secret"])
    link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
    expires_raw = sub["expires_at"][:10]  # "YYYY-MM-DD"
    expires_fmt = f"{expires_raw[8:10]}.{expires_raw[5:7]}.{expires_raw[:4]}"
    devices = sub.get("devices", 1)

    text = (
        f"<b>Ваша подписка:</b>\n\n"
        f"Статус подписки: активна {CE_SUCCESS}\n\n"
        f"Дата конца подписки: {expires_fmt} {CE_DURATION}\n\n"
        f"Устройств: {devices} {CE_DEVICES}\n\n"
        f"Ссылка: {link} {CE_LINK}\n\n"
        f"Нажмите на ссылку, затем нажмите подключиться {CE_SUCCESS}"
    )

    await callback.message.edit_media(
        _cover_media(text),
        reply_markup=proxies_kb,
    )
    await callback.answer()
