from __future__ import annotations

from io import BytesIO
from typing import List, Tuple

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from db.db import get_db
from services.utils import parse_bulk_text


router = Router()


class BulkStates(StatesGroup):
    waiting_input = State()
    confirm = State()


HELP_TEXT = (
    "Массовый импорт. Отправьте файл .csv/.txt или вставьте текст.\n\n"
    "Формат строк: Имя;ДД.ММ[.ГГГГ][;телефон][;tg] \n"
    "Примеры:\n"
    "Иван;12.02\n"
    "Маша;04.08.1995;+79991234567;@masha\n\n"
    "Допускаются разделители ; , или табуляция. Первая строка может быть шапкой: name,date,phone,tg"
)


@router.message(F.text == "/bulk")
@router.message(F.text == "Массовый импорт")
async def bulk_start(message: Message, state: FSMContext):
    await state.set_state(BulkStates.waiting_input)
    await message.answer(HELP_TEXT)


@router.message(BulkStates.waiting_input, F.document)
async def bulk_file(message: Message, state: FSMContext):
    # Ограничим размер до ~2 МБ
    if message.document.file_size and message.document.file_size > 2 * 1024 * 1024:
        await message.answer("Файл слишком большой (>2MB). Разбейте на части.")
        return
    buf = BytesIO()
    await message.bot.download(message.document, destination=buf)
    text = buf.getvalue().decode("utf-8", errors="ignore")
    await _process_bulk_text(message, state, text)


@router.message(BulkStates.waiting_input, F.text)
async def bulk_text(message: Message, state: FSMContext):
    await _process_bulk_text(message, state, message.text)


async def _process_bulk_text(message: Message, state: FSMContext, text: str):
    uid = message.from_user.id
    items, errors = parse_bulk_text(text)
    if not items and not errors:
        await message.answer("Не удалось распознать данные. Проверьте формат.")
        return
    await state.update_data(items=items)
    await state.set_state(BulkStates.confirm)
    ok = len(items)
    bad = len(errors)
    preview_err = ""
    if bad:
        preview = "\n".join(errors[:5])
        preview_err = f"\n\nОшибки (первые 5):\n{preview}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Импортировать", callback_data="bulk_import"), InlineKeyboardButton(text="Отмена", callback_data="bulk_cancel")]])
    await message.answer(f"Распознано записей: {ok}. Ошибок: {bad}.{preview_err}", reply_markup=kb)


@router.callback_query(BulkStates.confirm, F.data == "bulk_cancel")
async def bulk_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()


@router.callback_query(BulkStates.confirm, F.data == "bulk_import")
async def bulk_import(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("items", [])
    await state.clear()
    uid = call.from_user.id
    db = get_db()
    ok = 0
    skipped = 0
    for it in items:
        try:
            # проверка дубликатов по (friend, date)
            exists = await db.find_birthday_by_friend_date(uid, it["friend"].strip(), it["date"])
            if exists:
                skipped += 1
            else:
                await db.add_birthday(uid=uid, date=it["date"], friend=it["friend"].strip(), phone=it.get("phone"), tg_nic=it.get("tg_nic"))
                ok += 1
        except Exception:
            # пропускаем ошибочные
            continue
    await call.message.edit_text(f"Импорт завершён. Добавлено: {ok} из {len(items)}. Пропущено как дубликаты: {skipped}.")
    await call.answer()
