from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime as dt
import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.db import Database
from services.utils import get_age_text, human_date_short, today_mm_dd, today_str


def reminder_keyboard(birthday_id: int, with_link: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="Уже поздравил", callback_data=f"remind_done:{birthday_id}"),
            InlineKeyboardButton(text="Отложить", callback_data=f"remind_snooze:{birthday_id}"),
        ]
    ]
    if with_link:
        kb.append([InlineKeyboardButton(text="Привязать контакт", callback_data=f"link:{birthday_id}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@dataclass
class ReminderService:
    bot: Bot
    db: Database
    scheduler: AsyncIOScheduler
    interval_minutes: int = 60

    def start(self):
        # Periodic reminders with configurable interval
        # Первый запуск сразу после старта (next_run_time=now)
        try:
            now = dt.datetime.now(self.scheduler.timezone)
        except Exception:
            now = dt.datetime.now()
        self.scheduler.add_job(
            self._tick_job,
            "interval",
            minutes=self.interval_minutes,
            next_run_time=now,
        )
        # Daily reset at 00:05
        self.scheduler.add_job(self._daily_reset, CronTrigger(hour=0, minute=5))
        self.scheduler.start()

    async def _daily_reset(self):
        await self.db.reset_daily_flags()

    async def _tick_job(self):
        mm, dd = today_mm_dd()
        rows = await self.db.select_today_not_notified(mm, dd)
        logging.info(f"Reminder tick: found {len(rows)} birthday(s) for {mm}-{dd}")
        # Send reminders for each birthday
        for row in rows:
            uid = int(row["uid"])
            bid = int(row["id"]) 
            try:
                await self._send_or_replace_notification(uid, row)
            except Exception:
                # Ignore errors per-user to not block others
                continue

    async def _send_or_replace_notification(self, uid: int, row):
        bid = int(row["id"]) 
        last = await self.db.get_last_notification(uid, bid)
        if last:
            try:
                await self.bot.delete_message(chat_id=uid, message_id=int(last["message_id"]))
            except TelegramBadRequest:
                pass
            # delete extra if exists
            try:
                extra_id = last["extra_message_id"] if "extra_message_id" in last.keys() else None
                if extra_id:
                    await self.bot.delete_message(chat_id=uid, message_id=int(extra_id))
            except TelegramBadRequest:
                pass

        # Decide message type: text with link (if username present) or contact card (if phone present),
        # otherwise plain text with a button to link contact.
        tg_nic: Optional[str] = row["tg_nic"] if "tg_nic" in row.keys() else None
        phone: Optional[str] = row["phone"] if "phone" in row.keys() else None

        extra_id: int | None = None
        if tg_nic:
            text = self._build_message_text(row)
            msg = await self.bot.send_message(chat_id=uid, text=text, reply_markup=reminder_keyboard(bid))
        elif phone:
            # Send text first, then contact card so user sees context + has Write button
            text = self._build_message_text(row)
            extra = await self.bot.send_message(chat_id=uid, text=text, reply_markup=reminder_keyboard(bid))
            extra_id = extra.message_id
            friend = row["friend"]
            parts = friend.split(" ", 1)
            first_name = parts[0][:64]
            last_name = parts[1][:64] if len(parts) > 1 else None
            msg = await self.bot.send_contact(
                chat_id=uid,
                phone_number=str(phone),
                first_name=first_name,
                last_name=last_name,
                reply_markup=reminder_keyboard(bid),
            )
        else:
            text = self._build_message_text(row)
            msg = await self.bot.send_message(chat_id=uid, text=text, reply_markup=reminder_keyboard(bid, with_link=True))
        await self.db.upsert_last_notification(uid, bid, msg.message_id, today_str(), extra_message_id=extra_id)

    def _build_message_text(self, row) -> str:
        friend = row["friend"]
        date = row["date"]
        tg_nic: Optional[str] = row["tg_nic"] if "tg_nic" in row.keys() else None
        message = f"Сегодня день рождения у {friend} ({human_date_short(date)})! Не забудь поздравить!"
        age = get_age_text(date)
        if age:
            message += f"\nСегодня {friend} исполняется {age} 🎉"
        if tg_nic:
            nick = tg_nic.strip()
            if nick.startswith("@"):
                nick = nick[1:]
            message += f"\nПрофиль: https://t.me/{nick}"
        return message

    # Public handlers used by callbacks
    async def handle_done(self, uid: int, bid: int):
        await self.db.mark_notified_today(uid, bid)
        last = await self.db.get_last_notification(uid, bid)
        if last:
            try:
                await self.bot.delete_message(chat_id=uid, message_id=int(last["message_id"]))
            except TelegramBadRequest:
                pass
            try:
                extra_id = last["extra_message_id"] if "extra_message_id" in last.keys() else None
                if extra_id:
                    await self.bot.delete_message(chat_id=uid, message_id=int(extra_id))
            except TelegramBadRequest:
                pass
        await self.bot.send_message(chat_id=uid, text="Отлично! Больше не буду напоминать сегодня.")

    async def handle_snooze(self, uid: int, bid: int):
        # Отложить: удалить текущее уведомление и очистить запись last_notifications.
        # Новое уведомление придёт на следующем тике планировщика.
        row = await self.db.get_birthday(uid, bid)
        if not row:
            return
        last = await self.db.get_last_notification(uid, bid)
        if last:
            try:
                await self.bot.delete_message(chat_id=uid, message_id=int(last["message_id"]))
            except TelegramBadRequest:
                pass
            try:
                extra_id = last["extra_message_id"] if "extra_message_id" in last.keys() else None
                if extra_id:
                    await self.bot.delete_message(chat_id=uid, message_id=int(extra_id))
            except TelegramBadRequest:
                pass
            await self.db.delete_last_notification(uid, bid)
        # Ничего не отправляем сейчас — это и есть «отложить»
