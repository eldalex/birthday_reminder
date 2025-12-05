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
from services.utils import get_age_text, human_date_short, today_str


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
        # Periodic reminders aligned to wall clock boundaries.
        # If interval divides 60, use cron (*/N) to align to :00, :N, ...
        if self.interval_minutes >= 1 and 60 % self.interval_minutes == 0:
            step = self.interval_minutes
            if step == 60:
                trig = CronTrigger(minute=0)
            else:
                # APScheduler supports step notation
                trig = CronTrigger(minute=f"*/{step}")
            self.scheduler.add_job(self._tick_job, trig)
        else:
            # Fallback: interval trigger, align next run to the next boundary
            try:
                tznow = dt.datetime.now(self.scheduler.timezone)
            except Exception:
                tznow = dt.datetime.now()
            minute = tznow.minute
            step = max(1, self.interval_minutes)
            next_minute = ((minute // step) + 1) * step
            delta_min = next_minute - minute
            if delta_min <= 0:
                delta_min += step
            next_run = tznow.replace(second=0, microsecond=0) + dt.timedelta(minutes=delta_min)
            self.scheduler.add_job(
                self._tick_job,
                "interval",
                minutes=self.interval_minutes,
                next_run_time=next_run,
            )
        # Daily reset at 00:05
        self.scheduler.add_job(self._daily_reset, CronTrigger(hour=0, minute=5))
        self.scheduler.start()

    async def _daily_reset(self):
        await self.db.reset_daily_flags()

    async def _tick_job(self):
        await self.run_tick()

    async def run_tick(self, only_uid: int | None = None):
        # Подробное логирование «тика»: общее число ДР на сегодня, и по каждому пользователю
        try:
            now_utc = dt.datetime.utcnow()
        except Exception:
            now_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

        # Время «тика» в TZ планировщика
        try:
            tznow = dt.datetime.now(self.scheduler.timezone)
        except Exception:
            tznow = dt.datetime.now()
        tick_str = tznow.strftime("%H:%M")

        # Используем календарную дату по UTC для общего счёта, как и прежде
        mm_total = f"{now_utc.month:02d}"
        dd_total = f"{now_utc.day:02d}"
        try:
            all_today = await self.db.select_today_all(mm_total, dd_total)
            logging.info(f"В тик {tick_str} получено {len(all_today)} дня рождения")
        except Exception:
            logging.info(f"В тик {tick_str} получено неизвестно сколько дней рождений (ошибка выборки)")

        uids = await self.db.list_uids_with_birthdays()
        if only_uid is not None:
            uids = [uid for uid in uids if uid == only_uid]

        for uid in uids:
            # Персональные настройки
            try:
                prefs = await self.db.get_user_prefs(uid)
                tz_offset = int(prefs["tz_offset"]) if prefs else 0
                start_hour = int(prefs["start_hour"]) if prefs else 0
            except Exception:
                tz_offset, start_hour = 0, 0

            local_now = now_utc + dt.timedelta(hours=tz_offset)
            mm = f"{local_now.month:02d}"
            dd = f"{local_now.day:02d}"

            # Все сегодняшние ДР пользователя и те, которые ещё не напоминались
            try:
                rows_all = await self.db.select_user_today_all(uid, mm, dd)
            except Exception:
                rows_all = []
            try:
                rows_todo = await self.db.select_user_today_not_notified(uid, mm, dd)
            except Exception:
                rows_todo = []

            # Окно отправки: [start_hour, 23]
            if not (start_hour <= local_now.hour <= 23):
                sign = "+" if tz_offset >= 0 else ""
                logging.info(
                    f"пользователю {uid} отправлены 0 уведомлений. причина время не пришло, старт уведомлений с {start_hour:02d}:00 (UTC {sign}{tz_offset})"
                )
                continue

            sent = 0
            errors = 0
            for row in rows_todo:
                try:
                    await self._send_or_replace_notification(uid, row)
                    sent += 1
                except Exception as e:
                    errors += 1
                    logging.exception(f"Ошибка отправки уведомления пользователю {uid} по записи id={int(row['id'])}: {e}")

            already = max(0, len(rows_all) - len(rows_todo))
            # Сформируем текст по аналогии с примерами
            base = f"пользователю {uid} отправлены {sent} уведомления с напоминанием"
            tails: list[str] = []
            if already:
                tails.append(f"{already} не отправлено, причина уже поздравил")
            if errors:
                tails.append(f"{errors} не отправлено, причина ошибка отправки")
            msg = base + (", " + ", ".join(tails) if tails else "")
            logging.info(msg)

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
