import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import __version__ as aiogram_version

from config import load_settings
from db.db import init_database, get_db
from handlers import start, add, list as list_handler, edit, reminders as rem_handlers
from handlers import bulk
from handlers import link
from handlers import settings as settings_handler
from handlers import admin as admin_handler
from services.reminder_service import ReminderService


async def main():
    # Logging: console + file next to main.py
    log_path = Path(__file__).with_name("reminder.log")
    handlers = [logging.StreamHandler()]
    try:
        file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handlers.append(file_handler)
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings()
    if not settings.bot_token:
        logging.error("REMIND_BOT_TOKEN не задан. Установите переменную окружения REMIND_BOT_TOKEN и перезапустите.")
        return

    # DB
    db = init_database(settings.db_path)
    await db.initialize()

    # Bot & Dispatcher
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Health: getMe to validate token and log basic info
    try:
        me = await bot.get_me()
        logging.info(f"Bot OK: @{me.username} id={me.id}, aiogram={aiogram_version}")
    except Exception:
        logging.exception("Bot token check failed (getMe). Проверьте REMIND_BOT_TOKEN.")
        return

    # Bind admin UID to handlers (if provided)
    try:
        start.set_admin_uid(settings.admin_uid)
        admin_handler.set_admin_uid(settings.admin_uid)
    except Exception:
        pass

    # Routers
    dp.include_router(start.router)
    dp.include_router(add.router)
    dp.include_router(list_handler.router)
    dp.include_router(edit.router)
    dp.include_router(bulk.router)
    dp.include_router(link.router)
    dp.include_router(settings_handler.router)
    dp.include_router(rem_handlers.router)
    dp.include_router(admin_handler.router)

    # Scheduler & ReminderService
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    reminder_service = ReminderService(
        bot=bot,
        db=get_db(),
        scheduler=scheduler,
        interval_minutes=settings.reminder_interval_minutes,
    )
    rem_handlers.bind_reminder_service(reminder_service)
    reminder_service.start()
    logging.info(
        "Scheduler started: tz=%s, interval=%s min, jobs=%s",
        settings.timezone,
        settings.reminder_interval_minutes,
        len(scheduler.get_jobs()),
    )

    logging.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
