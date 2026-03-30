import asyncio
import logging
import re

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
    get_all_marketing_links, get_marketing_link_by_id,
    get_marketing_link_by_code, create_marketing_link,
    delete_marketing_link,
)

logger = logging.getLogger(__name__)

router = Router()


class AdminStates(StatesGroup):
    waiting_broadcast_message = State()
    waiting_marketing_link_code = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --- Admin panel entry ---

@router.message(Command("admin"))
async def handle_admin_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="🔗 Ссылки для блогеров", callback_data="admin_marketing_links"))
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
    builder.row(InlineKeyboardButton(text="🔗 Ссылки для блогеров", callback_data="admin_marketing_links"))
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


# --- Marketing links ---

@router.callback_query(F.data == "admin_marketing_links")
async def handle_admin_marketing_links(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    links = await get_all_marketing_links()

    builder = InlineKeyboardBuilder()
    for link in links[:20]:
        builder.row(InlineKeyboardButton(
            text=f"🔗 {link['code']} ({link['clicks_count']}/{link['paid_count']})",
            callback_data=f"admin_mlink_{link['id']}",
        ))
    builder.row(InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin_mlink_create"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))

    await callback.message.edit_text(
        "🔗 <b>Ссылки для блогеров</b>\n\n"
        "Формат: название (переходы/оплаты)\n\n"
        "Выберите ссылку для просмотра статистики или создайте новую:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_mlink_create")
async def handle_mlink_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_marketing_link_code)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_marketing_links"))

    bot_info = await callback.bot.get_me()

    await callback.message.edit_text(
        "🔗 <b>Создание ссылки для блогера</b>\n\n"
        "Введите название ссылки (только латиница, без пробелов):\n\n"
        f"Например: <code>mamix</code>\n"
        f"Диплинк будет: <code>t.me/{bot_info.username}?start=m_mamix</code>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.waiting_marketing_link_code)
async def handle_mlink_code_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    code = message.text.strip().lower()

    if not re.match(r'^[a-z0-9_-]+$', code):
        await message.answer(
            "❌ Название может содержать только латинские буквы, цифры, _ и -\n\n"
            "Попробуйте ещё раз:"
        )
        return

    existing = await get_marketing_link_by_code(code)
    if existing:
        await message.answer(
            f"❌ Ссылка с названием <code>{code}</code> уже существует.\n\n"
            "Введите другое название:",
            parse_mode="HTML",
        )
        return

    link = await create_marketing_link(code=code, created_by=message.from_user.id)

    await state.clear()

    bot_info = await message.bot.get_me()
    deeplink = f"https://t.me/{bot_info.username}?start=m_{code}"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать ещё", callback_data="admin_mlink_create"))
    builder.row(InlineKeyboardButton(text="📋 К списку", callback_data="admin_marketing_links"))
    builder.row(InlineKeyboardButton(text="🔙 В меню", callback_data="admin_back"))

    await message.answer(
        f"✅ <b>Ссылка создана!</b>\n\n"
        f"📝 Название: <code>{link['code']}</code>\n"
        f"🔗 Диплинк:\n<code>{deeplink}</code>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(
    F.data.startswith("admin_mlink_")
    & ~F.data.in_({"admin_mlink_create"})
    & ~F.data.startswith("admin_mlink_delete_")
    & ~F.data.startswith("admin_mlink_confirm_")
)
async def handle_mlink_detail(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    link_id = int(callback.data.replace("admin_mlink_", ""))
    link = await get_marketing_link_by_id(link_id)

    if not link:
        await callback.answer("Ссылка не найдена", show_alert=True)
        return

    bot_info = await callback.bot.get_me()
    deeplink = f"https://t.me/{bot_info.username}?start=m_{link['code']}"
    created = link["created_at"][:10] if link["created_at"] else "?"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_mlink_delete_{link['id']}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_marketing_links"))

    await callback.message.edit_text(
        f"🔗 <b>Ссылка: {link['code']}</b>\n\n"
        f"👥 Переходов: <b>{link['clicks_count']}</b>\n"
        f"💰 Оплат: <b>{link['paid_count']}</b>\n"
        f"📅 Создана: {created}\n\n"
        f"🔗 Диплинк:\n<code>{deeplink}</code>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_mlink_delete_"))
async def handle_mlink_delete_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    link_id = int(callback.data.replace("admin_mlink_delete_", ""))
    link = await get_marketing_link_by_id(link_id)

    if not link:
        await callback.answer("Ссылка не найдена", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_mlink_confirm_{link['id']}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_mlink_{link['id']}"))

    await callback.message.edit_text(
        f"🗑 <b>Удаление ссылки</b>\n\n"
        f"Вы уверены, что хотите удалить ссылку <code>{link['code']}</code>?\n\n"
        f"Статистика будет потеряна:\n"
        f"• Переходов: {link['clicks_count']}\n"
        f"• Оплат: {link['paid_count']}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_mlink_confirm_"))
async def handle_mlink_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    link_id = int(callback.data.replace("admin_mlink_confirm_", ""))
    deleted = await delete_marketing_link(link_id)

    if deleted:
        await callback.answer("✅ Ссылка удалена", show_alert=True)
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)
        return

    links = await get_all_marketing_links()

    builder = InlineKeyboardBuilder()
    for link in links[:20]:
        builder.row(InlineKeyboardButton(
            text=f"🔗 {link['code']} ({link['clicks_count']}/{link['paid_count']})",
            callback_data=f"admin_mlink_{link['id']}",
        ))
    builder.row(InlineKeyboardButton(text="➕ Создать ссылку", callback_data="admin_mlink_create"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))

    await callback.message.edit_text(
        "🔗 <b>Ссылки для блогеров</b>\n\n"
        "Формат: название (переходы/оплаты)\n\n"
        "Выберите ссылку для просмотра статистики или создайте новую:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


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
