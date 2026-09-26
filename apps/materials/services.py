"""Rates for other apps. The board (every active material with today's and
the previous price) is one query, cached for RATE_CACHE_SECONDS and dropped
whenever a rate is saved. Quotes, bookings and weigh sheets read prices from
it, so the server, not the client, owns every price (contract 14)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.cache import cache
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.common.formatting import iso

from .messages import msg
from .models import Material, MaterialRate

CACHE_VERSION_KEY = "rates:version"


@dataclass(frozen=True)
class RateRow:
    id: int
    name_en: str
    name_ne: str
    abbr: str
    category: str
    price_per_kg: int
    previous_price: int | None
    published_at: object

    def name(self, lang: str) -> str:
        return self.name_ne if lang == "ne" and self.name_ne else self.name_en

    @property
    def trend(self) -> tuple[float, str]:
        if not self.previous_price or self.previous_price == self.price_per_kg:
            return 0.0, "flat"
        change = (Decimal(self.price_per_kg - self.previous_price) / Decimal(self.previous_price)) * 100
        percent = float(abs(change).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        return percent, "up" if change > 0 else "down"


def _cache_key(city: str, day) -> str:
    version = cache.get(CACHE_VERSION_KEY) or 0
    return f"rates:board:{version}:{city}:{day.isoformat()}"


def invalidate_board() -> None:
    try:
        cache.incr(CACHE_VERSION_KEY)
    except ValueError:
        cache.set(CACHE_VERSION_KEY, 1, timeout=None)


def board(city: str | None = None) -> list[RateRow]:
    """Every active material that has a rate today, highest price first."""
    city = city or settings.DEFAULT_CITY
    today = timezone.localdate()
    key = _cache_key(city, today)
    rows = cache.get(key)
    if rows is not None:
        return rows

    rates = MaterialRate.objects.filter(material=OuterRef("pk"), city=city, effective_date__lte=today).order_by(
        "-effective_date"
    )
    materials = (
        Material.objects.filter(is_active=True)
        .annotate(
            current_price=Subquery(rates.values("price_per_kg")[:1]),
            previous_price=Subquery(rates.values("price_per_kg")[1:2]),
            current_published=Subquery(rates.values("published_at")[:1]),
        )
        .filter(current_price__isnull=False)
    )
    rows = sorted(
        (
            RateRow(
                id=m.id,
                name_en=m.name_en,
                name_ne=m.name_ne,
                abbr=m.abbr,
                category=m.category,
                price_per_kg=m.current_price,
                previous_price=m.previous_price,
                published_at=m.current_published,
            )
            for m in materials
        ),
        key=lambda r: (-r.price_per_kg, r.id),
    )
    cache.set(key, rows, timeout=settings.RATE_CACHE_SECONDS)
    return rows


def rate_map(city: str | None = None) -> dict[int, RateRow]:
    return {row.id: row for row in board(city)}


def rate_dict(row: RateRow, lang: str) -> dict:
    """The Rate shape (contract 6)."""
    percent, direction = row.trend
    return {
        "id": row.id,
        "name": row.name(lang),
        "abbr": row.abbr,
        "category": row.category,
        "price_per_kg": row.price_per_kg,
        "trend_percent": percent,
        "trend_direction": direction,
    }


def updated_at(rows: list[RateRow]) -> str | None:
    stamps = [r.published_at for r in rows if r.published_at]
    return iso(max(stamps)) if stamps else None


def categories(lang: str) -> list[dict]:
    return [{"id": value, "label": msg(f"category_{value}", lang)} for value in Material.Category.values]


def material_names(material_ids, lang: str) -> dict[int, str]:
    """Names for ids, including retired materials (used in history)."""
    return {m.id: m.name(lang) for m in Material.objects.filter(id__in=set(material_ids))}
