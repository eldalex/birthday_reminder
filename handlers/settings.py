from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from db.db import get_db


router = Router()


class SettingsStates(StatesGroup):
    waiting_tz = State()
    waiting_hour = State()


def settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить часовой пояс", callback_data="set_tz")],
            [InlineKeyboardButton(text="Изменить стартовый час", callback_data="set_hour")],
            [InlineKeyboardButton(text="Готово", callback_data="settings_cancel")],
        ]
    )


async def _get_prefs_text(uid: int) -> str:
    db = get_db()
    prefs = await db.get_user_prefs(uid)
    tz = int(prefs["tz_offset"]) if prefs else 0
    hour = int(prefs["start_hour"]) if prefs else 0
    sign = "+" if tz >= 0 else ""
    return (
        "Настройки уведомлений:\n"
        f"• Часовой пояс: UTC{sign}{tz}\n"
        f"• Начинать слать с: {hour:02d}:00 (до 23:00)\n\n"
        "Можно изменить:"
    )


@router.message(F.text == "/settings")
@router.message(F.text == "Настройки")
async def settings_entry(message: Message, state: FSMContext):
    text = await _get_prefs_text(message.from_user.id)
    msg = await message.answer(text, reply_markup=settings_menu_kb())
    await state.update_data(control_mid=msg.message_id, control_mids=[msg.message_id], user_mids=[])


@router.callback_query(F.data == "set_tz")
async def set_tz_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_tz)
    await state.update_data(control_mid=call.message.message_id)
    prompt = "Введите ваш часовой пояс относительно UTC. Примеры: +3, -1, 0. Диапазон: -12..+14."
    try:
        await call.message.edit_text(
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="settings_cancel")]]
            ),
        )
    except TelegramBadRequest:
        pass
    await call.answer()


def _parse_tz(text: str) -> int:
    s = text.strip().upper().replace("UTC", "")
    if s.startswith("GMT"):
        s = s[3:]
    s = s.strip()
    if s.startswith("+") or s.startswith("-"):
        pass
    else:
        # bare number like 3 or 0
        if s and s[0].isdigit():
            s = "+" + s
    try:
        val = int(s)
    except Exception:
        raise ValueError("Введите целое число, например +3 или -1")
    if val < -12 or val > 14:
        raise ValueError("Допустимый диапазон: от -12 до +14")
    return val


@router.message(SettingsStates.waiting_tz)
async def set_tz_apply(message: Message, state: FSMContext):
    try:
        tz = _parse_tz(message.text)
    except ValueError as e:
        # Показать ошибку в том же контрол-сообщении
        data = await state.get_data()
        control_mid = data.get("control_mid")
        try:
            if control_mid:
                await message.bot.edit_message_text(chat_id=message.from_user.id, message_id=int(control_mid), text=str(e), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="settings_cancel")]]))
        except TelegramBadRequest:
            pass
        # удалить невалидный ввод
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return
    db = get_db()
    prefs = await db.get_user_prefs(message.from_user.id)
    start_hour = int(prefs["start_hour"]) if prefs else 0
    await db.upsert_user_prefs(uid=message.from_user.id, tz_offset=tz, start_hour=start_hour)
    # удалить пользовательский ввод
    data = await state.get_data()
    mids = list(data.get("user_mids", []))
    mids.append(message.message_id)
    for mid in mids:
        try:
            await message.bot.delete_message(chat_id=message.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    await state.update_data(user_mids=[])
    # Вернуть меню в контрол сообщении
    text = await _get_prefs_text(message.from_user.id)
    control_mid = data.get("control_mid")
    try:
        if control_mid:
            await message.bot.edit_message_text(chat_id=message.from_user.id, message_id=int(control_mid), text=text, reply_markup=settings_menu_kb())
    except TelegramBadRequest:
        pass
    await state.clear()


@router.callback_query(F.data == "set_hour")
async def set_hour_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_hour)
    await state.update_data(control_mid=call.message.message_id)
    prompt = "С какого часа начинать напоминать? Введите число 0..23. Например: 10"
    try:
        await call.message.edit_text(
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="settings_cancel")]]
            ),
        )
    except TelegramBadRequest:
        pass
    await call.answer()


@router.message(SettingsStates.waiting_hour)
async def set_hour_apply(message: Message, state: FSMContext):
    s = message.text.strip()
    if not s.isdigit():
        data = await state.get_data()
        control_mid = data.get("control_mid")
        try:
            if control_mid:
                await message.bot.edit_message_text(chat_id=message.from_user.id, message_id=int(control_mid), text="Введите число от 0 до 23", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="settings_cancel")]]))
        except TelegramBadRequest:
            pass
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return
    val = int(s)
    if not (0 <= val <= 23):
        data = await state.get_data()
        control_mid = data.get("control_mid")
        try:
            if control_mid:
                await message.bot.edit_message_text(chat_id=message.from_user.id, message_id=int(control_mid), text="Введите число от 0 до 23", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="settings_cancel")]]))
        except TelegramBadRequest:
            pass
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        return
    db = get_db()
    prefs = await db.get_user_prefs(message.from_user.id)
    tz = int(prefs["tz_offset"]) if prefs else 0
    await db.upsert_user_prefs(uid=message.from_user.id, tz_offset=tz, start_hour=val)
    # удалить пользовательский ввод
    data = await state.get_data()
    mids = list(data.get("user_mids", []))
    mids.append(message.message_id)
    for mid in mids:
        try:
            await message.bot.delete_message(chat_id=message.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    await state.update_data(user_mids=[])
    # Вернуть меню в контрол сообщении
    text = await _get_prefs_text(message.from_user.id)
    control_mid = data.get("control_mid")
    try:
        if control_mid:
            await message.bot.edit_message_text(chat_id=message.from_user.id, message_id=int(control_mid), text=text, reply_markup=settings_menu_kb())
    except TelegramBadRequest:
        pass
    await state.clear()


@router.callback_query(F.data == "settings_cancel")
async def settings_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    control_mids = list(data.get("control_mids", []) or [])
    user_mids = list(data.get("user_mids", []) or [])
    for mid in control_mids:
        try:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    for mid in user_mids:
        try:
            await call.bot.delete_message(chat_id=call.from_user.id, message_id=int(mid))
        except TelegramBadRequest:
            pass
    await state.clear()
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.answer()
