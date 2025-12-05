from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message

from db.db import get_db


router = Router()


_ADMIN_UID: int | None = None


def set_admin_uid(uid: int | None) -> None:
    global _ADMIN_UID
    _ADMIN_UID = uid


async def _is_admin(uid: int) -> bool:
    return _ADMIN_UID is not None and uid == _ADMIN_UID


@router.message(F.text == "/users")
@router.message(F.text == "Пользователи")
async def users_stats(message: Message):
    uid = message.from_user.id
    if not await _is_admin(uid):
        return
    db = get_db()
    # per-user stats
    rows = await db.list_user_record_counts()
    lines = [f"пользователь {int(r['uid'])}: {int(r['c'])} записей" for r in rows]
    total_users = await db.count_unique_users()
    total_records = await db.count_total_records()
    lines.append("")
    lines.append(f"Уникальных пользователей: {total_users}; Всего записей: {total_records}")
    await message.answer("\n".join(lines) or "Нет данных")
