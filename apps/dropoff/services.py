from django.conf import settings
from django.utils import timezone

from apps.common.formatting import clock
from apps.common.geo import bounding_box, distance_km, round_km

from .models import DropoffCenter


def centers_near(lat, lng, radius_km: float) -> list[tuple[DropoffCenter, float]]:
    """Active centers within `radius_km`, nearest first."""
    candidates = DropoffCenter.objects.filter(is_active=True, **bounding_box(lat, lng, radius_km))
    found = []
    for center in candidates:
        km = distance_km(lat, lng, center.lat, center.lng)
        if km <= radius_km:
            found.append((center, km))
    found.sort(key=lambda pair: pair[1])
    return found


def nearest_center(lat, lng) -> dict | None:
    """{"id", "name", "distance_km"} of the closest active center, or null."""
    found = centers_near(lat, lng, settings.DROPOFF_MAX_RADIUS_KM)
    if not found:
        return None
    center, km = found[0]
    return {"id": str(center.id), "name": center.name, "distance_km": round_km(km)}


def nearby_summary(lat, lng) -> dict | None:
    """Home card: {"center_count", "radius_km", "open_till"} (contract 5.1)."""
    radius = settings.DROPOFF_DEFAULT_RADIUS_KM
    found = centers_near(lat, lng, radius)
    now = timezone.localtime().time()
    open_closing = [c.closes_at for c, _ in found if c.is_open_at(now)]
    return {
        "center_count": len(found),
        "radius_km": radius,
        "open_till": clock(max(open_closing)) if open_closing else None,
    }


def center_dict(center: DropoffCenter, km: float, now) -> dict:
    return {
        "id": str(center.id),
        "name": center.name,
        "address": center.address,
        "lat": float(center.lat),
        "lng": float(center.lng),
        "distance_km": round_km(km),
        "phone": center.phone or None,
        "open_now": center.is_open_at(now),
        "opens_at": clock(center.opens_at),
        "closes_at": clock(center.closes_at),
        "accepts": list(center.accepts or []),
    }
