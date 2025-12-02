from __future__ import annotations

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.exceptions import TelegramBadRequest

from db.db import get_db
from services.utils import parse_date_input, human_date_short


router = Router()


class EditStates(StatesGroup):
    waiting_value = State()


def edit_menu_kb(bid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Имя", callback_data=f"edit_field:{bid}:friend")],
        [InlineKeyboardButton(text="Дата", callback_data=f"edit_field:{bid}:date")],
        [InlineKeyboardButton(text="Телефон", callback_data=f"edit_field:{bid}:phone")],
        [InlineKeyboardButton(text="TG username", callback_data=f"edit_field:{bid}:tg_nic")],
        [InlineKeyboardButton(text="Привязать контакт", callback_data=f"link:{bid}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{bid}")],
        [InlineKeyboardButton(text="Отмена", callback_data="edit_cancel")],
    ])


@router.callback_query(F.data.startswith("edit:"))
async def edit_open(call: CallbackQuery):
    bid = int(call.data.split(":", 1)[1])
    db = get_db()
    row = await db.get_birthday(call.from_user.id, bid)
    if not row:
        await call.answer("Запись не найдена", show_alert=True)
        return
    text = f"Редактирование: {row['friend']} — {human_date_short(row['date'])}"
    await call.message.edit_text(text, reply_markup=edit_menu_kb(bid))
    await call.answer()


@router.callback_query(F.data.startswith("edit_field:"))
async def edit_field_choose(call: CallbackQuery, state: FSMContext):
    _, rest = call.data.split(":", 1)
    bid_s, field = rest.split(":", 1)
    bid = int(bid_s)
    await state.set_state(EditStates.waiting_value)
    await state.update_data(bid=bid, field=field)
    prompts = {
        "friend": "Новое имя:",
        "date": "Новая дата (ДД.ММ или ДД.ММ.ГГГГ):",
        "phone": "Новый телефон (или пусто):",
        "tg_nic": "Новый TG username (или пусто):",
    }
    await call.message.answer(prompts.get(field, "Введите значение:"))
    await call.answer()


@router.message(EditStates.waiting_value)
async def edit_apply(message: Message, state: FSMContext):
    data = await state.get_data()
    bid = int(data["bid"]) 
    field = data["field"]
    value_raw = message.text.strip()

    if field == "date":
        try:
            norm, _ = parse_date_input(value_raw)
        except ValueError as e:
            await message.answer(str(e))
            return
        value = norm
    else:
        value = value_raw if value_raw else None

    db = get_db()
    await db.update_birthday_field(message.from_user.id, bid, field, value)
    await state.clear()
    await message.answer("Сохранено.")


@router.callback_query(F.data == "edit_cancel")
async def edit_cancel(call: CallbackQuery):
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("del:"))
async def delete_confirm(call: CallbackQuery):
    bid = int(call.data.split(":", 1)[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=f"del_yes:{bid}"),
            InlineKeyboardButton(text="Нет", callback_data=f"del_no:{bid}"),
        ]
    ])
    await call.message.edit_text("Точно удалить?", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("del_yes:"))
async def delete_yes(call: CallbackQuery):
    bid = int(call.data.split(":", 1)[1])
    await get_db().delete_birthday(call.from_user.id, bid)
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("del_no:"))
async def delete_no(call: CallbackQuery):
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.answer()
