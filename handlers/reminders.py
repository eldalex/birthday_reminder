from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

from db.db import get_db
from services.reminder_service import ReminderService


router = Router()


# These will be set from main when ReminderService is constructed
reminder_service: ReminderService | None = None


def bind_reminder_service(service: ReminderService):
    global reminder_service
    reminder_service = service


@router.callback_query(F.data.startswith("remind_done:"))
async def cb_done(call: CallbackQuery):
    bid = int(call.data.split(":", 1)[1])
    if reminder_service:
        await reminder_service.handle_done(call.from_user.id, bid)
    await call.answer()


@router.callback_query(F.data.startswith("remind_snooze:"))
async def cb_snooze(call: CallbackQuery):
    bid = int(call.data.split(":", 1)[1])
    if reminder_service:
        await reminder_service.handle_snooze(call.from_user.id, bid)
    await call.answer()

