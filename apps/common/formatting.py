"""Value formatting shared by every endpoint: ISO datetimes in Nepal time,
weights, clock times, and the Bikram Sambat labels the app shows as-is
("15 Bhadra", "Sun 10") so the client needs no BS calendar."""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

import nepali_datetime
from django.utils import timezone

BS_MONTHS = {
    "en": [
        "Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Asoj",
        "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
    ],
    "ne": ["बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज", "कात्तिक", "मंसिर", "पुस", "माघ", "फागुन", "चैत"],
}  # fmt: skip

WEEKDAYS_SHORT = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ne": ["सोम", "मंगल", "बुध", "बिही", "शुक्र", "शनि", "आइत"],
}
WEEKDAYS_LONG = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ne": ["सोमबार", "मंगलबार", "बुधबार", "बिहीबार", "शुक्रबार", "शनिबार", "आइतबार"],
}

# Nepal's fiscal year starts on 1 Shrawan (BS month 4).
FISCAL_YEAR_START_MONTH = 4


def iso(value: dt.datetime | None) -> str | None:
    """'2026-09-13T10:30:00+05:45': local time, whole seconds."""
    if value is None:
        return None
    return timezone.localtime(value).replace(microsecond=0).isoformat()


def iso_date(value: dt.date | None) -> str | None:
    return value.isoformat() if value else None


def clock(value: dt.time | None) -> str | None:
    """'18:00'."""
    return value.strftime("%H:%M") if value else None


def money(value) -> int:
    """Integer rupees, half-up rounding (Python's round() is banker's)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def kg(value) -> int | float | None:
    """Weights as a JSON number with at most one decimal: 14 or 29.3."""
    if value is None:
        return None
    rounded = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return int(rounded) if rounded == rounded.to_integral_value() else float(rounded)


def bs(value: dt.date) -> nepali_datetime.date:
    return nepali_datetime.date.from_datetime_date(value)


def bs_day_month(value: dt.date, lang: str) -> str:
    """'15 Bhadra'."""
    d = bs(value)
    return f"{d.day} {BS_MONTHS.get(lang, BS_MONTHS['en'])[d.month - 1]}"


def day_label(value: dt.date | None, lang: str) -> str | None:
    """'Sun 10': short weekday + BS day of month."""
    if value is None:
        return None
    return f"{WEEKDAYS_SHORT.get(lang, WEEKDAYS_SHORT['en'])[value.weekday()]} {bs(value).day}"


def long_day_label(value: dt.date, lang: str) -> str:
    """'Sunday 10'."""
    return f"{WEEKDAYS_LONG.get(lang, WEEKDAYS_LONG['en'])[value.weekday()]} {bs(value).day}"


def slot_label(start: dt.datetime | None, end: dt.datetime | None) -> str | None:
    """'8:00 – 9:00' (no leading zero on the hour)."""
    if start is None or end is None:
        return None
    s, e = timezone.localtime(start), timezone.localtime(end)
    return f"{s.hour}:{s.minute:02d} – {e.hour}:{e.minute:02d}"


def fiscal_year(today: dt.date | None = None) -> tuple[str, dt.date]:
    """(label, first AD day) of the current BS fiscal year, e.g. ('2083', 2026-07-17)."""
    today = today or timezone.localdate()
    d = bs(today)
    year = d.year if d.month >= FISCAL_YEAR_START_MONTH else d.year - 1
    start = nepali_datetime.date(year, FISCAL_YEAR_START_MONTH, 1).to_datetime_date()
    return str(year), start
