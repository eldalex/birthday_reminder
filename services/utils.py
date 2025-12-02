from __future__ import annotations

import datetime as dt
from typing import Optional, Tuple
import csv
import io


def parse_date_input(text: str) -> Tuple[str, str]:
    """
    Parse 'DD.MM' or 'DD.MM.YYYY' and return:
    - normalized 'YYYY-MM-DD' (year '0000' if not provided)
    - display string 'DD.MM' or 'DD.MM.YYYY'
    Raises ValueError if invalid.
    """
    s = text.strip().replace(" ", "")
    parts = s.split(".")
    if len(parts) not in (2, 3):
        raise ValueError("Неверный формат даты. Используйте ДД.ММ или ДД.ММ.ГГГГ")
    try:
        day = int(parts[0])
        month = int(parts[1])
    except ValueError:
        raise ValueError("День и месяц должны быть числами")
    if not (1 <= day <= 31 and 1 <= month <= 12):
        raise ValueError("Некорректный день или месяц")
    if len(parts) == 3 and parts[2]:
        try:
            year = int(parts[2])
        except ValueError:
            raise ValueError("Год должен быть числом")
        if not (1900 <= year <= 2100):
            raise ValueError("Год вне диапазона 1900-2100")
    else:
        year = 0

    # validate actual date if year provided, otherwise basic day range per month
    if year:
        try:
            dt.date(year, month, day)
        except ValueError:
            raise ValueError("Такой даты не существует")
    else:
        # pick leap-safe year for validation, e.g., 2000
        try:
            dt.date(2000, month, day)
        except ValueError:
            raise ValueError("Такой даты не существует")

    norm = f"{year:04d}-{month:02d}-{day:02d}"
    disp = f"{day:02d}.{month:02d}" + (f".{year:04d}" if year else "")
    return norm, disp


def human_date_short(date: str) -> str:
    # date: 'YYYY-MM-DD' (year may be 0000)
    year = date[:4]
    mm = date[5:7]
    dd = date[8:10]
    return f"{dd}.{mm}" if year == "0000" else f"{dd}.{mm}.{year}"


def get_age_text(date: str) -> Optional[str]:
    year = date[:4]
    if year == "0000":
        return None
    try:
        y = int(year)
        m = int(date[5:7])
        d = int(date[8:10])
        today = dt.date.today()
        age = today.year - y - ((today.month, today.day) < (m, d))
        if age < 0:
            return None
        return str(age)
    except Exception:
        return None


def today_mm_dd() -> tuple[str, str]:
    t = dt.date.today()
    return f"{t.month:02d}", f"{t.day:02d}"


def today_str() -> str:
    t = dt.date.today()
    return t.strftime("%Y-%m-%d")


def days_until_next(date_str: str, today: Optional[dt.date] = None) -> int:
    """Return number of days until next occurrence of given YYYY-MM-DD (year may be 0000).
    Handles 29 Feb by mapping to 28 Feb on non-leap years.
    """
    if today is None:
        today = dt.date.today()
    m = int(date_str[5:7])
    d = int(date_str[8:10])
    year = today.year
    try:
        candidate = dt.date(year, m, d)
    except ValueError:
        # 29 Feb fallback to 28 Feb on non-leap years
        if m == 2 and d == 29:
            candidate = dt.date(year, 2, 28)
        else:
            # fallback to next month/day validation using 2000
            candidate = dt.date(year, m, min(d, 28))
    if candidate < today:
        year += 1
        try:
            candidate = dt.date(year, m, d)
        except ValueError:
            if m == 2 and d == 29:
                candidate = dt.date(year, 2, 28)
            else:
                candidate = dt.date(year, m, min(d, 28))
    return (candidate - today).days


def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[";", ",", "\t"])  # type: ignore[arg-type]
        return dialect.delimiter  # type: ignore[attr-defined]
    except Exception:
        # Heuristics
        if sample.count(";") >= sample.count(",") and sample.count(";") >= sample.count("\t"):
            return ";"
        if sample.count(",") >= sample.count("\t"):
            return ","
        return "\t"


def parse_bulk_text(text: str) -> tuple[list[dict], list[str]]:
    """Parse multiline CSV/text into list of {friend,date,phone?,tg_nic?} and errors.
    - Accepts optional header (name/friend, date, phone, tg/tg_nic/username)
    - Accepts ; , or tab delimiters
    - Blank lines are ignored
    - Date format: DD.MM or DD.MM.YYYY
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return [], []
    sample = "\n".join(lines[:5])
    delim = _sniff_delimiter(sample)
    buf = io.StringIO("\n".join(lines))
    reader = csv.reader(buf, delimiter=delim)

    headers = None
    peek = lines[0].lower()
    if any(h in peek for h in ["name", "имя", "friend"]) and ("date" in peek or "дата" in peek):
        headers = next(reader, None)

    def norm_header(h: str) -> str:
        h = h.strip().lower()
        mapping = {
            "name": "friend",
            "имя": "friend",
            "friend": "friend",
            "date": "date",
            "дата": "date",
            "phone": "phone",
            "телефон": "phone",
            "tg": "tg_nic",
            "username": "tg_nic",
            "tg_nic": "tg_nic",
        }
        return mapping.get(h, h)

    items: list[dict] = []
    errors: list[str] = []

    if headers:
        idx = {norm_header(h): i for i, h in enumerate(headers)}
        for i, row in enumerate(reader, start=2):
            try:
                friend = row[idx.get("friend", 0)].strip()
                date_raw = row[idx.get("date", 1)].strip()
                phone = row[idx["phone"]].strip() if "phone" in idx and idx["phone"] < len(row) else None
                tg = row[idx["tg_nic"]].strip() if "tg_nic" in idx and idx["tg_nic"] < len(row) else None
                norm, _ = parse_date_input(date_raw)
                if tg and tg.startswith("@"): tg = tg[1:]
                if not friend:
                    raise ValueError("пустое имя")
                items.append({"friend": friend, "date": norm, "phone": phone or None, "tg_nic": tg or None})
            except Exception as e:
                errors.append(f"Строка {i}: {e}")
    else:
        for i, row in enumerate(reader, start=1):
            try:
                # friend;date;[phone];[tg]
                if len(row) < 2:
                    raise ValueError("ожидалось минимум 2 колонки")
                friend = row[0].strip()
                date_raw = row[1].strip()
                phone = row[2].strip() if len(row) > 2 else None
                tg = row[3].strip() if len(row) > 3 else None
                norm, _ = parse_date_input(date_raw)
                if tg and tg.startswith("@"): tg = tg[1:]
                if not friend:
                    raise ValueError("пустое имя")
                items.append({"friend": friend, "date": norm, "phone": phone or None, "tg_nic": tg or None})
            except Exception as e:
                errors.append(f"Строка {i}: {e}")
    return items, errors
