import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from db import (
    get_users_count, get_active_subscriptions_count,
    get_payments_stats, get_all_user_ids,
)

logger = logging.getLogger(__name__)

router = Router()


class AdminStates(StatesGroup):
    waiting_broadcast_message = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --- Admin panel entry ---

@router.message(Command("admin"))
async def handle_admin_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))

    await message.answer(
        "🔐 <b>Админ-панель</b>\n\n"
        "Выберите раздел:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "admin_back")
async def handle_admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))

    await callback.message.edit_text(
        "🔐 <b>Админ-панель</b>\n\n"
        "Выберите раздел:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


# --- Stats ---

@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    users = await get_users_count()
    active_subs = await get_active_subscriptions_count()
    payments = await get_payments_stats()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))

    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"⚡ Активных подписок: <b>{active_subs}</b>\n"
        f"💰 Успешных оплат: <b>{payments['paid_count']}</b>\n"
        f"💵 Выручка: <b>{payments['total_revenue']:.0f}₽</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


# --- Broadcast ---

@router.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_broadcast_message)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back"))

    users_count = await get_users_count()

    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        f"👥 Пользователей в базе: {users_count}\n\n"
        "Отправьте сообщение для рассылки.\n\n"
        "Поддерживается:\n"
        "• Текст (с HTML-форматированием)\n"
        "• Фото с подписью",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_message, F.photo)
async def handle_broadcast_photo(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    photo_id = message.photo[-1].file_id
    caption = message.caption or ""

    await state.update_data(photo_id=photo_id, caption=caption, text=None)
    await state.set_state(None)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧪 Тест (админам)", callback_data="broadcast_test"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back"))

    await message.answer_photo(
        photo=photo_id,
        caption=f"{caption}\n\n<i>👆 Предпросмотр сообщения</i>" if caption else "<i>👆 Предпросмотр сообщения</i>",
        parse_mode="HTML",
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(),
    )


@router.message(AdminStates.waiting_broadcast_message, F.text)
async def handle_broadcast_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    text = message.text

    await state.update_data(text=text, photo_id=None, caption=None)
    await state.set_state(None)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧪 Тест (админам)", callback_data="broadcast_test"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back"))

    await message.answer(
        f"{text}\n\n<i>👆 Предпросмотр сообщения</i>",
        parse_mode="HTML",
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "broadcast_test")
async def handle_broadcast_test(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    bot: Bot = callback.bot
    await callback.answer("Отправляю тест админам...")

    sent = 0
    failed = 0

    for admin_id in ADMIN_IDS:
        try:
            if data.get("photo_id"):
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=data["photo_id"],
                    caption=data.get("caption") or None,
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=data.get("text", ""),
                    parse_mode="HTML",
                )
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to send test to admin {admin_id}: {e}")
            failed += 1
        await asyncio.sleep(0.1)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Отправить ВСЕМ", callback_data="broadcast_all"))
    builder.row(InlineKeyboardButton(text="✏️ Изменить", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back"))

    await callback.message.edit_text(
        f"🧪 <b>Тестовая рассылка завершена</b>\n\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}\n\n"
        f"Теперь можете отправить всем пользователям.",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "broadcast_all")
async def handle_broadcast_all(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()

    if not data.get("text") and not data.get("photo_id"):
        await callback.answer("Сначала создайте сообщение", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 <b>Рассылка запущена...</b>\n\nПодождите, это может занять время.",
        parse_mode="HTML",
    )
    await callback.answer()

    bot: Bot = callback.bot
    user_ids = await get_all_user_ids()

    total = len(user_ids)
    sent = 0
    failed = 0

    for i, telegram_id in enumerate(user_ids):
        try:
            if data.get("photo_id"):
                await bot.send_photo(
                    chat_id=telegram_id,
                    photo=data["photo_id"],
                    caption=data.get("caption") or None,
                    parse_mode="HTML",
                )
            else:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=data.get("text", ""),
                    parse_mode="HTML",
                )
            sent += 1
        except Exception as e:
            logger.warning(f"Failed to send to user {telegram_id}: {e}")
            failed += 1

        if (i + 1) % 30 == 0:
            await asyncio.sleep(1)
        else:
            await asyncio.sleep(0.05)

    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 В меню", callback_data="admin_back"))

    await callback.message.edit_text(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"👥 Всего: {total}\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
