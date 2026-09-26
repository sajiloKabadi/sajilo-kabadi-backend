"""Prices and fees (contract 8.3). The client never sends a price: amounts
come from today's rate board and these rules only."""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from rest_framework import status

from apps.common.exceptions import ApiError
from apps.common.formatting import kg, money
from apps.materials.services import RateRow, rate_map

from .messages import msg
from .models import Pickup


@dataclass
class PricedLine:
    rate: RateRow
    approx_kg: Decimal

    @property
    def amount(self) -> int:
        return money(Decimal(self.rate.price_per_kg) * self.approx_kg)


def price_items(items: list[dict], lang: str) -> list[PricedLine]:
    """[{material_id, approx_kg}] -> priced lines, or 400 material_not_found."""
    rates = rate_map()
    missing = [item["material_id"] for item in items if item["material_id"] not in rates]
    if missing:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "material_not_found",
            msg("material_not_found", lang),
            errors={"items": [msg("material_not_found_item", lang, id=m) for m in missing]},
        )
    return [PricedLine(rates[item["material_id"]], item["approx_kg"]) for item in items]


def delivery_fee(option: str, total_kg: Decimal, distance_km) -> int:
    if option == Pickup.DeliveryOption.COLLECTOR_PICKUP:
        return 0 if total_kg >= settings.PICKUP_FREE_ABOVE_KG else settings.PICKUP_SMALL_LOAD_FEE
    if option == Pickup.DeliveryOption.TRUCK_HELPER:
        km = Decimal(str(distance_km or 0))
        return settings.TRUCK_BASE_FEE + money(Decimal(settings.TRUCK_FEE_PER_KM) * km)
    return 0


def collector_earning(total_kg: Decimal, fee: int) -> int:
    """The collector's cut shown as "You earn (estimate)" (contract 12.3):
    a per-kg handling amount (with a floor) plus the delivery fee."""
    handling = max(settings.COLLECTOR_EARNING_MIN, money(Decimal(settings.COLLECTOR_EARNING_PER_KG) * total_kg))
    return handling + fee


def quote(lines: list[PricedLine], option: str, distance_km, lang: str) -> dict:
    total_kg = sum((line.approx_kg for line in lines), Decimal("0"))
    materials_total = sum(line.amount for line in lines)
    fee = delivery_fee(option, total_kg, distance_km)
    return {
        "items": [
            {
                "material_id": line.rate.id,
                "name": line.rate.name(lang),
                "price_per_kg": line.rate.price_per_kg,
                "approx_kg": kg(line.approx_kg),
                "amount": line.amount,
            }
            for line in lines
        ],
        "total_kg": kg(total_kg),
        "materials_total": materials_total,
        "delivery_fee": fee,
        "estimated_payout": max(materials_total - fee, 0),
        "is_estimate": True,
    }
