"""Response shapes for pickups, jobs, weigh sheets and disputes, as plain
dicts field-for-field with the contract."""

import datetime as dt
import math
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count
from django.utils import timezone

from apps.accounts.presenters import avatar_url, display_name
from apps.common.formatting import day_label, iso, iso_date, kg, long_day_label, money, slot_label
from apps.common.geo import distance_km, round_km

from .messages import msg
from .models import COLLECTOR_WORKING_STATUSES, Pickup, PickupRating, WeighFlag, WeighSheet
from .pricing import delivery_fee

TIMELINE_STEPS = ("requested", "matched", "on_the_way", "arrived", "weighing")
STEP_INDEX = {
    Pickup.Status.REQUESTED: 0,
    Pickup.Status.MATCHED: 1,
    Pickup.Status.ON_THE_WAY: 2,
    Pickup.Status.ARRIVED: 3,
    Pickup.Status.WEIGHING: 4,
    Pickup.Status.DISPUTED: 4,
}
STEP_TIME_FIELD = {
    "requested": "created_at",
    "matched": "matched_at",
    "on_the_way": "on_the_way_at",
    "arrived": "arrived_at",
    "weighing": "weighing_at",
}


def ratings_for(user_ids) -> dict:
    """{user_id: (average, count)} for many users in one query."""
    rows = (
        PickupRating.objects.filter(ratee_id__in=set(user_ids))
        .values("ratee_id")
        .annotate(avg=Avg("stars"), n=Count("id"))
    )
    return {row["ratee_id"]: (round(float(row["avg"]), 1), row["n"]) for row in rows}


def phone_visible(pickup: Pickup) -> bool:
    """Phones are shared only while the pickup is active, and for 24 h after
    completion (contract 14)."""
    if pickup.status in (*COLLECTOR_WORKING_STATUSES, Pickup.Status.DISPUTED):
        return True
    if pickup.status == Pickup.Status.COMPLETED and pickup.completed_at:
        return pickup.completed_at >= timezone.now() - dt.timedelta(hours=settings.PHONE_VISIBLE_HOURS_AFTER)
    return False


def _item_count(pickup: Pickup) -> int:
    count = getattr(pickup, "item_count", None)
    return count if count is not None else len(pickup.items.all())


def summary_dict(pickup: Pickup, lang: str, request=None) -> dict:
    """The next_pickup shape (contract 5.1), also used by GET /pickups/."""
    collector = pickup.collector
    return {
        "id": str(pickup.id),
        "ref": pickup.ref,
        "status": pickup.status,
        "scheduled_date": iso_date(pickup.scheduled_date),
        "day_label": day_label(pickup.scheduled_date, lang),
        "slot_start": iso(pickup.slot_start),
        "slot_end": iso(pickup.slot_end),
        "slot_label": slot_label(pickup.slot_start, pickup.slot_end),
        "item_count": _item_count(pickup),
        "approx_weight_kg": kg(pickup.approx_weight_kg),
        "collector": (
            {
                "id": str(collector.id),
                "name": display_name(collector),
                "phone": collector.phone_number if phone_visible(pickup) else None,
                "avatar_url": avatar_url(collector, request),
            }
            if collector
            else None
        ),
    }


def when_label(pickup: Pickup, lang: str, long: bool = False) -> str:
    day = (long_day_label if long else day_label)(pickup.scheduled_date, lang)
    slot = slot_label(pickup.slot_start, pickup.slot_end)
    return f"{day} · {slot}" if slot else day


def _eta_minutes(pickup: Pickup, profile) -> int | None:
    if pickup.status != Pickup.Status.ON_THE_WAY or profile is None or not profile.has_location:
        return None
    km = distance_km(profile.last_lat, profile.last_lng, pickup.lat, pickup.lng)
    return max(1, math.ceil(km / settings.COLLECTOR_AVG_SPEED_KMH * 60))


def _timeline(pickup: Pickup, lang: str, collector_first_name: str | None) -> list[dict]:
    def label(step):
        if step in ("matched", "arrived"):
            return (
                msg(f"tl_{step}", lang, name=collector_first_name)
                if collector_first_name
                else msg(f"tl_{step}_anon", lang)
            )
        return msg(f"tl_{step}", lang)

    def entry(step, state):
        return {"key": step, "label": label(step), "at": iso(getattr(pickup, STEP_TIME_FIELD[step])), "state": state}

    if pickup.status == Pickup.Status.COMPLETED:
        return [entry(step, "done") for step in TIMELINE_STEPS]
    if pickup.status in (Pickup.Status.CANCELLED, Pickup.Status.EXPIRED):
        reached = [s for s in TIMELINE_STEPS if getattr(pickup, STEP_TIME_FIELD[s])]
        at = pickup.cancelled_at if pickup.status == Pickup.Status.CANCELLED else pickup.expired_at
        terminal = {"key": pickup.status, "label": msg(f"tl_{pickup.status}", lang), "at": iso(at), "state": "current"}
        return [entry(s, "done") for s in reached] + [terminal]

    current = STEP_INDEX[pickup.status]
    return [
        entry(step, "done" if i < current else "current" if i == current else "pending")
        for i, step in enumerate(TIMELINE_STEPS)
    ]


def detail_dict(pickup: Pickup, lang: str, request=None, ratings: dict | None = None) -> dict:
    """GET /pickups/{id}/ (contract 8.6)."""
    collector = pickup.collector
    profile = getattr(collector, "collector_profile", None) if collector else None
    collector_block = None
    updated = pickup.updated_at
    if collector:
        ratings = ratings if ratings is not None else ratings_for([collector.id])
        location = None
        if (
            pickup.status in (Pickup.Status.ON_THE_WAY, Pickup.Status.ARRIVED)
            and profile is not None
            and profile.has_location
        ):
            location = {
                "lat": float(profile.last_lat),
                "lng": float(profile.last_lng),
                "heading": profile.last_heading,
                "updated_at": iso(profile.last_location_at),
            }
            if profile.last_location_at and profile.last_location_at > updated:
                updated = profile.last_location_at
        collector_block = {
            "id": str(collector.id),
            "name": display_name(collector),
            "initials": collector.initials,
            "avatar_url": avatar_url(collector, request),
            "phone": collector.phone_number if phone_visible(pickup) else None,
            "rating": ratings.get(collector.id, (None, 0))[0],
            "vehicle_number": (profile.vehicle_number or None) if profile else None,
            "location": location,
            "eta_minutes": _eta_minutes(pickup, profile),
        }

    items = list(pickup.items.all())
    return {
        "id": str(pickup.id),
        "ref": pickup.ref,
        "status": pickup.status,
        "created_at": iso(pickup.created_at),
        "scheduled_date": iso_date(pickup.scheduled_date),
        "day_label": day_label(pickup.scheduled_date, lang),
        "slot_start": iso(pickup.slot_start),
        "slot_end": iso(pickup.slot_end),
        "slot_label": slot_label(pickup.slot_start, pickup.slot_end),
        "when_label": when_label(pickup, lang, long=True),
        "delivery_option": pickup.delivery_option,
        "address": {
            "id": str(pickup.address_id) if pickup.address_id else None,
            "line": pickup.address_line,
            "lat": float(pickup.lat),
            "lng": float(pickup.lng),
        },
        "items": [
            {"material_id": i.material_id, "name": i.material.name(lang), "approx_kg": kg(i.approx_kg)} for i in items
        ],
        "approx_weight_kg": kg(pickup.approx_weight_kg),
        "estimated_total": pickup.estimated_total,
        "delivery_fee": pickup.delivery_fee,
        "estimated_payout": pickup.estimated_payout,
        "final_total": pickup.final_total,
        "collector": collector_block,
        "timeline": _timeline(pickup, lang, collector.display_first_name if collector else None),
        "can_cancel": pickup.status in (Pickup.Status.REQUESTED, Pickup.Status.MATCHED),
        "weigh_sheet_available": pickup.status
        in (Pickup.Status.WEIGHING, Pickup.Status.DISPUTED, Pickup.Status.COMPLETED)
        and hasattr(pickup, "weigh_sheet"),
        "updated_at": iso(updated),
        "poll_after": settings.POLL_ON_THE_WAY_SECONDS
        if pickup.status == Pickup.Status.ON_THE_WAY
        else settings.POLL_DEFAULT_SECONDS,
    }


def job_dict(pickup: Pickup, lang: str, origin=None, ratings: dict | None = None) -> dict:
    """An open job for collectors (contract 12.3)."""
    seller = pickup.seller
    ratings = ratings if ratings is not None else ratings_for([seller.id])
    distance = None
    if origin is not None and origin[0] is not None:
        distance = round_km(distance_km(origin[0], origin[1], pickup.lat, pickup.lng))
    return {
        "id": str(pickup.id),
        "ref": pickup.ref,
        "seller": {
            "name": display_name(seller),
            "initials": seller.initials,
            "rating": ratings.get(seller.id, (None, 0))[0],
        },
        "area": pickup.area,
        "address": pickup.address_line,
        "lat": float(pickup.lat),
        "lng": float(pickup.lng),
        "distance_km": distance,
        "scheduled_date": iso_date(pickup.scheduled_date),
        "day_label": day_label(pickup.scheduled_date, lang),
        "slot_label": slot_label(pickup.slot_start, pickup.slot_end),
        "slot_start": iso(pickup.slot_start),
        "slot_end": iso(pickup.slot_end),
        "materials": [i.material.name(lang) for i in pickup.items.all()],
        "approx_weight_kg": kg(pickup.approx_weight_kg),
        "delivery_option": pickup.delivery_option,
        "estimated_earning": pickup.collector_earning,
    }


def job_detail_dict(pickup: Pickup, lang: str, viewer, origin=None) -> dict:
    """12.3 item + note + seller.phone (only for the accepting collector) + status."""
    data = job_dict(pickup, lang, origin)
    owns = pickup.collector_id == viewer.id
    data["seller"]["phone"] = pickup.seller.phone_number if owns and phone_visible(pickup) else None
    data["note"] = pickup.note or None
    data["status"] = pickup.status
    return data


def sheet_totals(pickup: Pickup, lines) -> tuple[Decimal, int, int, int]:
    """(total_kg, total, delivery_fee, payout): fee re-computed from the real weight."""
    total_kg = sum((line.kg for line in lines), Decimal("0"))
    total = sum(money(Decimal(line.rate_per_kg) * line.kg) for line in lines)
    fee = delivery_fee(pickup.delivery_option, total_kg, pickup.distance_km)
    return total_kg, total, fee, max(total - fee, 0)


def sheet_dict(pickup: Pickup, sheet: WeighSheet, lang: str) -> dict:
    """GET /pickups/{id}/weigh-sheet/ (contract 9.1); also the collector's view."""
    lines = list(sheet.lines.select_related("material"))
    flags = {}
    for flag in WeighFlag.objects.filter(sheet=sheet).order_by("created_at"):
        # Latest flag per line, open ones win.
        current = flags.get(flag.material_id)
        if current is None or flag.status == WeighFlag.Status.OPEN or current.status != WeighFlag.Status.OPEN:
            flags[flag.material_id] = flag

    total_kg, total, fee, payout = sheet_totals(pickup, lines)
    collector = pickup.collector
    return {
        "pickup_id": str(pickup.id),
        "status": sheet.status,
        "version": sheet.version,
        "collector": {"first_name": collector.display_first_name if collector else None},
        "lines": [
            {
                "id": line.line_id,
                "material_id": line.material_id,
                "material": line.material.name(lang),
                "rate_per_kg": line.rate_per_kg,
                "kg": kg(line.kg),
                "amount": money(Decimal(line.rate_per_kg) * line.kg),
                "flag": (
                    {"id": str(f.id), "reason": f.reason, "status": f.status}
                    if (f := flags.get(line.material_id))
                    else None
                ),
            }
            for line in lines
        ],
        "total_kg": kg(total_kg),
        "total": total,
        "delivery_fee": fee,
        "payout": payout,
        "can_accept": sheet.status == WeighSheet.Status.SUBMITTED,
        "updated_at": iso(sheet.updated_at),
        "poll_after": settings.POLL_WEIGH_LIVE_SECONDS
        if sheet.status == WeighSheet.Status.LIVE
        else settings.POLL_DEFAULT_SECONDS,
    }


def dispute_dict(dispute, lang: str) -> dict:
    closed = dispute.status != dispute.Status.OPEN
    return {
        "id": str(dispute.id),
        "pickup_ref": dispute.pickup.ref,
        "type": dispute.type,
        "status": dispute.status,
        "title": msg(f"dispute_{dispute.type}", lang),
        "created_at": iso(dispute.created_at),
        "resolution": (
            {"note": dispute.resolution_note or None, "adjusted_amount": dispute.adjusted_amount} if closed else None
        ),
    }


def delivery_options(lang: str) -> list[dict]:
    fmt = {
        "free_kg": settings.PICKUP_FREE_ABOVE_KG,
        "fee": settings.PICKUP_SMALL_LOAD_FEE,
        "base": settings.TRUCK_BASE_FEE,
        "per_km": settings.TRUCK_FEE_PER_KM,
    }
    return [
        {
            "id": option,
            "title": msg(f"opt_{option}_title", lang),
            "subtitle": msg(f"opt_{option}_subtitle", lang, **fmt),
            "needs_slot": option != Pickup.DeliveryOption.SELF_DROPOFF,
        }
        for option in Pickup.DeliveryOption.values
    ]
