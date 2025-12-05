import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    bot_token: str
    db_path: str = "db/birthdays.sqlite3"
    timezone: str = os.getenv("TZ", "UTC")
    reminder_interval_minutes: int = 2
    admin_uid: Optional[int] = None


def load_settings() -> Settings:
    token = os.getenv("REMIND_BOT_TOKEN", "")
    if not token:
        # Пользователь должен выставить переменную окружения REMIND_BOT_TOKEN
        pass
    db_path = os.getenv("DB_PATH", "db/birthdays.sqlite3")
    # Частота напоминаний, мин. — по умолчанию 60
    interval_env = os.getenv("REMINDER_INTERVAL_MINUTES", "60")
    try:
        interval = int(interval_env)
    except ValueError:
        interval = 60
    # Безопасный минимум 5 минут
    if interval < 5:
        interval = 5
    # Admin UID (optional)
    admin_s = os.getenv("ADMIN_UID", "").strip()
    admin_uid: Optional[int]
    try:
        admin_uid = int(admin_s) if admin_s else None
    except ValueError:
        admin_uid = None

    return Settings(
        bot_token=token,
        db_path=db_path,
        reminder_interval_minutes=interval,
        admin_uid=admin_uid,
    )
