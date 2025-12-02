import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import load_settings
from db.db import init_database, get_db
from handlers import start, add, list as list_handler, edit, reminders as rem_handlers
from handlers import bulk
from handlers import link
from services.reminder_service import ReminderService


async def main():
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    if not settings.bot_token:
        print("[WARN] BOT_TOKEN не задан. Установите переменную окружения BOT_TOKEN перед запуском.")

    # DB
    db = init_database(settings.db_path)
    await db.initialize()

    # Bot & Dispatcher
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Routers
    dp.include_router(start.router)
    dp.include_router(add.router)
    dp.include_router(list_handler.router)
    dp.include_router(edit.router)
    dp.include_router(bulk.router)
    dp.include_router(link.router)
    dp.include_router(rem_handlers.router)

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

    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
