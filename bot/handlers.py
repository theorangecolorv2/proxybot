from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from urllib.parse import quote

from config import PROXY_HOST, PROXY_PORT
from db import add_user, get_active_subscriptions, create_payment
from secret_gen import make_tls_link_secret
from payment import create_yookassa_payment
from pricing import get_device_price, get_discount, calculate_total

router = Router()

CE_ZAP = '<tg-emoji emoji-id="5219943216781995020">⚡</tg-emoji>'
CE_CONNECT = '<tg-emoji emoji-id="5454386656628991407">🔗</tg-emoji>'


class BuyFlow(StatesGroup):
    choosing_devices = State()
    entering_custom_devices = State()
    choosing_duration = State()
    entering_custom_duration = State()
    confirming = State()


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить подписку", callback_data="buy_sub")],
        [InlineKeyboardButton(text="Мои прокси", callback_data="my_proxies")],
    ])


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


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", callback_data="confirm_pay")],
        [InlineKeyboardButton(text="← Назад", callback_data="back_to_duration")],
    ])


# --- /start ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await add_user(message.from_user.id, message.from_user.username)
    subs = await get_active_subscriptions(message.from_user.id)

    if subs:
        sub = subs[0]
        link_secret = make_tls_link_secret(sub["secret"])
        link = f"tg://proxy?server={quote(PROXY_HOST)}&port={PROXY_PORT}&secret={link_secret}"
        await message.answer(
            f"Отличного настроения! 💛\n\n"
            f"С нами телеграмм всегда доступен! ✈️\n\n"
            f"Ваш прокси: {link}",
            reply_markup=main_keyboard(),
        )
    else:
        await message.answer(
            f"Отличного настроения! 💛\n\n"
            f"С нами телеграмм всегда доступен! ✈️\n\n"
            f"Купите подписку, чтобы всегда быть на связи📞",
            reply_markup=main_keyboard(),
        )


# --- Step 1: Choose devices ---

@router.callback_query(F.data == "buy_sub")
async def buy_sub(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.choosing_devices)
    await callback.message.edit_text(
        "Выберите количество устройств:",
        reply_markup=devices_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dev_"), BuyFlow.choosing_devices)
async def pick_device_count(callback: CallbackQuery, state: FSMContext):
    count_str = callback.data.split("_")[1]
    if count_str == "custom":
        await state.set_state(BuyFlow.entering_custom_devices)
        await callback.message.edit_text(
            "Введите количество устройств (от 1 до 100):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back_to_devices")],
            ]),
        )
        await callback.answer()
        return

    devices = int(count_str)
    await state.update_data(devices=devices)
    await state.set_state(BuyFlow.choosing_duration)
    await callback.message.edit_text(
        f"Устройств: {devices}\nВыберите срок подписки:",
        reply_markup=duration_keyboard(devices),
    )
    await callback.answer()


@router.message(BuyFlow.entering_custom_devices)
async def enter_custom_devices(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    if not text.isdigit() or not (1 <= int(text) <= 100):
        await message.answer(
            "Введите число от 1 до 100:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← Назад", callback_data="back_to_devices")],
            ]),
        )
        return

    devices = int(text)
    await state.update_data(devices=devices)
    await state.set_state(BuyFlow.choosing_duration)
    await message.answer(
        f"Устройств: {devices}\nВыберите срок подписки:",
        reply_markup=duration_keyboard(devices),
    )


# --- Step 2: Choose duration ---

@router.callback_query(F.data.startswith("dur_"), BuyFlow.choosing_duration)
async def pick_duration(callback: CallbackQuery, state: FSMContext):
    dur_str = callback.data.split("_")[1]
    if dur_str == "custom":
        await state.set_state(BuyFlow.entering_custom_duration)
        await callback.message.edit_text(
            "Введите количество месяцев (от 1 до 36):",
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
        await message.answer(
            "Введите число от 1 до 36:",
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

    text = (
        f"<b>Ваш заказ:</b>\n\n"
        f"Устройств: {devices}\n"
        f"Срок: {months} мес.\n"
        f"Цена за месяц: {price_per_month}₽\n"
    )
    if discount > 0:
        text += f"Скидка: {discount}%\n"
    text += f"\n<b>Итого: {total}₽</b>"

    await state.set_state(BuyFlow.confirming)
    if edit:
        await msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=confirm_keyboard())
    else:
        await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=confirm_keyboard())


# --- Step 3: Confirm & pay ---

@router.callback_query(F.data == "confirm_pay", BuyFlow.confirming)
async def confirm_pay(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    devices = data["devices"]
    months = data["months"]
    telegram_id = callback.from_user.id

    try:
        result = create_yookassa_payment(telegram_id, devices, months)
    except Exception:
        await callback.message.edit_text(
            "Ошибка при создании платежа. Попробуйте позже.",
            reply_markup=main_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    await create_payment(telegram_id, result["payment_id"], result["amount"], devices, months)
    await state.clear()

    total = calculate_total(devices, months)
    await callback.message.edit_text(
        f"<b>Прокси: {devices} устр., {months} мес.</b> — {total}₽\n\n"
        f"После оплаты прокси будет создан автоматически.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=result["confirmation_url"])],
            [InlineKeyboardButton(text="← Назад", callback_data="back_to_menu")],
        ]),
    )
    await callback.answer()


# --- Back buttons ---

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        f"{CE_ZAP} <b>MTProxy для Telegram</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_devices")
async def back_to_devices(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.choosing_devices)
    await callback.message.edit_text(
        "Выберите количество устройств:",
        reply_markup=devices_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_duration")
async def back_to_duration(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    devices = data.get("devices", 1)
    await state.set_state(BuyFlow.choosing_duration)
    await callback.message.edit_text(
        f"Устройств: {devices}\nВыберите срок подписки:",
        reply_markup=duration_keyboard(devices),
    )
    await callback.answer()


# --- My proxies ---

@router.callback_query(F.data == "my_proxies")
async def my_proxies(callback: CallbackQuery):
    subs = await get_active_subscriptions(callback.from_user.id)

    if not subs:
        await callback.message.edit_text(
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

    await callback.message.edit_text(
        f"<b>Ваши прокси:</b>\n\n" + "\n\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )
    await callback.answer()
