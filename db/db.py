import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional


class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(Path(path).parent, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")

    async def initialize(self):
        sql_path = Path(__file__).with_name("birthdays.sql")
        schema_sql = sql_path.read_text(encoding="utf-8")
        await self.execute_script(schema_sql)
        # ensure new columns for existing DBs
        await self._ensure_columns()

    async def _ensure_columns(self) -> None:
        def run():
            cur = self._conn.execute("PRAGMA table_info(birthdays)")
            cols = {row[1] for row in cur.fetchall()}
            with self._conn:
                if "tg_id" not in cols:
                    self._conn.execute("ALTER TABLE birthdays ADD COLUMN tg_id INTEGER NULL")
                # last_notifications extra column
                cur2 = self._conn.execute("PRAGMA table_info(last_notifications)")
                cols2 = {row[1] for row in cur2.fetchall()}
                if "extra_message_id" not in cols2:
                    self._conn.execute("ALTER TABLE last_notifications ADD COLUMN extra_message_id INTEGER NULL")

        await asyncio.to_thread(run)

    async def execute(self, query: str, params: Iterable[Any] | None = None) -> None:
        def run():
            with self._conn:
                self._conn.execute(query, tuple(params or []))

        await asyncio.to_thread(run)

    async def execute_script(self, script: str) -> None:
        def run():
            with self._conn:
                self._conn.executescript(script)

        await asyncio.to_thread(run)

    async def fetchone(self, query: str, params: Iterable[Any] | None = None) -> Optional[sqlite3.Row]:
        def run():
            cur = self._conn.execute(query, tuple(params or []))
            return cur.fetchone()

        return await asyncio.to_thread(run)

    async def fetchall(self, query: str, params: Iterable[Any] | None = None) -> list[sqlite3.Row]:
        def run():
            cur = self._conn.execute(query, tuple(params or []))
            return cur.fetchall()

        return await asyncio.to_thread(run)

    # Domain-specific helpers
    async def add_birthday(self, uid: int, date: str, friend: str, phone: Optional[str], tg_nic: Optional[str] = None) -> int:
        def run() -> int:
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO birthdays (uid, date, friend, phone, tg_nic, already_remaind) VALUES (?, ?, ?, ?, ?, 0)",
                    (uid, date, friend, phone, tg_nic),
                )
                return int(cur.lastrowid)

        return await asyncio.to_thread(run)

    async def find_birthday_by_friend_date(self, uid: int, friend: str, date: str) -> Optional[int]:
        row = await self.fetchone(
            "SELECT id FROM birthdays WHERE uid = ? AND friend = ? AND date = ?",
            (uid, friend, date),
        )
        return int(row["id"]) if row else None

    async def update_birthday_field(self, uid: int, bid: int, field: str, value: Any) -> bool:
        assert field in {"date", "friend", "phone", "tg_nic", "tg_id", "already_remaind"}
        res = await self.execute(
            f"UPDATE birthdays SET {field} = ? WHERE id = ? AND uid = ?",
            (value, bid, uid),
        )
        # sqlite doesn't return rowcount without cursor access; verify existence on fetch if needed.
        return True

    async def get_birthday(self, uid: int, bid: int) -> Optional[sqlite3.Row]:
        return await self.fetchone("SELECT * FROM birthdays WHERE id = ? AND uid = ?", (bid, uid))

    async def delete_birthday(self, uid: int, bid: int) -> None:
        await self.execute("DELETE FROM birthdays WHERE id = ? AND uid = ?", (bid, uid))
        # Also cleanup last notifications for this record
        await self.execute("DELETE FROM last_notifications WHERE uid = ? AND birthday_id = ?", (uid, bid))

    async def list_birthdays_page(self, uid: int, limit: int, offset: int) -> list[sqlite3.Row]:
        return await self.fetchall(
            "SELECT * FROM birthdays WHERE uid = ? ORDER BY substr(date, 6, 2), substr(date, 9, 2), friend LIMIT ? OFFSET ?",
            (uid, limit, offset),
        )

    async def list_birthdays_all(self, uid: int) -> list[sqlite3.Row]:
        return await self.fetchall(
            "SELECT * FROM birthdays WHERE uid = ?",
            (uid,),
        )

    async def count_birthdays(self, uid: int) -> int:
        row = await self.fetchone("SELECT COUNT(*) AS c FROM birthdays WHERE uid = ?", (uid,))
        return int(row["c"]) if row else 0

    async def select_today_not_notified(self, mm: str, dd: str) -> list[sqlite3.Row]:
        like = f"%-{mm}-{dd}"
        return await self.fetchall(
            "SELECT * FROM birthdays WHERE date LIKE ? AND already_remaind = 0",
            (like,),
        )

    async def mark_notified_today(self, uid: int, bid: int) -> None:
        await self.execute("UPDATE birthdays SET already_remaind = 1 WHERE id = ? AND uid = ?", (bid, uid))

    # last_notifications helpers
    async def get_last_notification(self, uid: int, bid: int) -> Optional[sqlite3.Row]:
        return await self.fetchone(
            "SELECT * FROM last_notifications WHERE uid = ? AND birthday_id = ?",
            (uid, bid),
        )

    async def upsert_last_notification(
        self, uid: int, bid: int, message_id: int, date: str, extra_message_id: int | None = None
    ) -> None:
        await self.execute(
            "INSERT INTO last_notifications(uid, birthday_id, message_id, date, extra_message_id) VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(uid, birthday_id) DO UPDATE SET message_id = excluded.message_id, date = excluded.date, extra_message_id = excluded.extra_message_id",
            (uid, bid, message_id, date, extra_message_id),
        )

    async def delete_last_notification(self, uid: int, bid: int) -> None:
        await self.execute("DELETE FROM last_notifications WHERE uid = ? AND birthday_id = ?", (uid, bid))

    async def reset_daily_flags(self) -> None:
        await self.execute("UPDATE birthdays SET already_remaind = 0")


_db: Database | None = None


def init_database(path: str) -> Database:
    global _db
    _db = Database(path)
    return _db


def get_db() -> Database:
    assert _db is not None, "Database is not initialized"
    return _db
