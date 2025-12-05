-- Schema for birthdays and last_notifications tables

CREATE TABLE IF NOT EXISTS birthdays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    date TEXT NOT NULL,              -- format: YYYY-MM-DD (year may be '0000' if unknown)
    friend TEXT NOT NULL,
    phone TEXT NULL,
    tg_nic TEXT NULL,
    tg_id INTEGER NULL,
    already_remaind INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_birthdays_uid ON birthdays(uid);
CREATE INDEX IF NOT EXISTS idx_birthdays_date ON birthdays(date);

-- For preventing spam: track last sent notification per (uid, birthday_id)
CREATE TABLE IF NOT EXISTS last_notifications (
    uid INTEGER NOT NULL,
    birthday_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    date TEXT NOT NULL,              -- YYYY-MM-DD of when it was sent
    extra_message_id INTEGER NULL,
    PRIMARY KEY (uid, birthday_id)
);

-- Per-user preferences: timezone offset (hours) and start hour for notifications
CREATE TABLE IF NOT EXISTS user_prefs (
    uid INTEGER PRIMARY KEY,
    tz_offset INTEGER NOT NULL DEFAULT 0,   -- e.g., +3, -1
    start_hour INTEGER NOT NULL DEFAULT 0   -- 0..23; send from this hour until 23:00 local
);
