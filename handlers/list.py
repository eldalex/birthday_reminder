from __future__ import annotations

from math import ceil

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from db.db import get_db
from services.utils import human_date_short, days_until_next


router = Router()


PAGE_SIZE = 5


def list_keyboard(items: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for r in items:
        bid = int(r["id"]) 
        title = f"{r['friend']} — {human_date_short(r['date'])}"
        rows.append([InlineKeyboardButton(text=title, callback_data=f"edit:{bid}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page:{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"page:{page+1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows or [[]])


async def render_list(message: Message, page: int, uid: int):
    db = get_db()
    rows_all = await db.list_birthdays_all(uid)
    if not rows_all:
        await message.answer("Список пуст. Добавьте первую запись командой /add или кнопкой.")
        return
    # sort by days until next birthday ascending
    rows_all_sorted = sorted(rows_all, key=lambda r: days_until_next(r['date']))
    total = len(rows_all_sorted)
    total_pages = max(1, ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PAGE_SIZE
    rows = rows_all_sorted[offset: offset + PAGE_SIZE]

    lines = []
    for i, r in enumerate(rows, start=1 + offset):
        lines.append(f"{i}. {r['friend']} — {human_date_short(r['date'])}")
    text = "\n".join(lines) + f"\n\nСтр. {page}/{total_pages}"
    await message.answer(text, reply_markup=list_keyboard(rows, page, total_pages))


@router.message(F.text == "/list")
@router.message(F.text == "Список друзей")
async def list_command(message: Message):
    await render_list(message, page=1, uid=message.from_user.id)


@router.callback_query(F.data.startswith("page:"))
async def list_page(call: CallbackQuery):
    page = int(call.data.split(":", 1)[1])
    await call.message.delete()
    await render_list(call.message, page, uid=call.from_user.id)
    await call.answer()
