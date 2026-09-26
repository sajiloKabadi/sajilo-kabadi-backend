"""Bookable days and slots (contract 8.2). Slots are the configured
PICKUP_SLOTS on each of the next PICKUP_DAYS_AHEAD days; a slot is
unavailable once it starts within PICKUP_MIN_LEAD_MINUTES or holds
PICKUP_SLOT_CAPACITY active bookings. Booked counts come from one query."""

import datetime as dt
from collections import Counter
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from apps.common.formatting import WEEKDAYS_SHORT, bs, iso, slot_label

from .models import ACTIVE_STATUSES, Pickup

SLOT_ID_FORMAT = "%Y-%m-%dT%H:%M"


@dataclass(frozen=True)
class Slot:
    start: dt.datetime
    end: dt.datetime

    @property
    def id(self) -> str:
        return timezone.localtime(self.start).strftime(SLOT_ID_FORMAT)


def slot_times() -> list[tuple[dt.time, dt.time]]:
    times = []
    for spec in settings.PICKUP_SLOTS:
        start, end = spec.split("-")
        times.append((dt.time.fromisoformat(start.strip()), dt.time.fromisoformat(end.strip())))
    return times


def _aware(day: dt.date, clock: dt.time) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, clock))


def upcoming_days() -> list[dt.date]:
    today = timezone.localdate()
    return [today + dt.timedelta(days=i) for i in range(settings.PICKUP_DAYS_AHEAD)]


def _booked_counts(first: dt.datetime, last: dt.datetime) -> Counter:
    rows = (
        Pickup.objects.filter(status__in=ACTIVE_STATUSES, slot_start__gte=first, slot_start__lte=last)
        .values("slot_start")
        .annotate(n=Count("id"))
    )
    return Counter({row["slot_start"]: row["n"] for row in rows})


def _cutoff() -> dt.datetime:
    return timezone.now() + dt.timedelta(minutes=settings.PICKUP_MIN_LEAD_MINUTES)


def days(lang: str) -> list[dict]:
    dates = upcoming_days()
    times = slot_times()
    counts = _booked_counts(_aware(dates[0], times[0][0]), _aware(dates[-1], times[-1][0]))
    cutoff = _cutoff()
    today = timezone.localdate()

    result = []
    for day in dates:
        slots = []
        for start_t, end_t in times:
            slot = Slot(_aware(day, start_t), _aware(day, end_t))
            slots.append(
                {
                    "id": slot.id,
                    "start": iso(slot.start),
                    "end": iso(slot.end),
                    "label": slot_label(slot.start, slot.end),
                    "available": slot.start > cutoff and counts[slot.start] < settings.PICKUP_SLOT_CAPACITY,
                }
            )
        result.append(
            {
                "date": day.isoformat(),
                "weekday": WEEKDAYS_SHORT.get(lang, WEEKDAYS_SHORT["en"])[day.weekday()],
                "day_label": str(bs(day).day),
                "is_today": day == today,
                "slots": slots,
            }
        )
    return result


def parse_slot(slot_id: str) -> Slot | None:
    """A configured slot on an upcoming day, or None."""
    try:
        start_local = dt.datetime.strptime(slot_id, SLOT_ID_FORMAT)
    except (TypeError, ValueError):
        return None
    if start_local.date() not in upcoming_days():
        return None
    for start_t, end_t in slot_times():
        if start_t == start_local.time():
            return Slot(_aware(start_local.date(), start_t), _aware(start_local.date(), end_t))
    return None


def slot_is_available(slot: Slot) -> bool:
    """Checked again inside the booking lock, so capacity can't be oversold."""
    if slot.start <= _cutoff():
        return False
    booked = Pickup.objects.filter(status__in=ACTIVE_STATUSES, slot_start=slot.start).count()
    return booked < settings.PICKUP_SLOT_CAPACITY
