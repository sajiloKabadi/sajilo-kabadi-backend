from decimal import Decimal

from django.utils import timezone

from apps.common.geo import bounding_box, distance_km

from .models import CollectorProfile, LocationPing


def _dec(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def record_location(user, lat, lng, heading=None, accuracy_m=None, recorded_at=None) -> CollectorProfile:
    """Store a ping and move the collector's last known position forward
    (older, out-of-order pings are kept in history but don't rewind it)."""
    recorded_at = recorded_at or timezone.now()
    LocationPing.objects.create(
        collector=user, lat=_dec(lat), lng=_dec(lng), heading=heading, accuracy_m=accuracy_m, recorded_at=recorded_at
    )
    profile, _ = CollectorProfile.objects.get_or_create(user=user)
    if profile.last_location_at is None or recorded_at >= profile.last_location_at:
        profile.last_lat, profile.last_lng = _dec(lat), _dec(lng)
        profile.last_heading = heading
        profile.last_location_at = recorded_at
        profile.save(update_fields=["last_lat", "last_lng", "last_heading", "last_location_at", "updated_at"])
    return profile


def online_collectors_near(lat, lng, radius_km: float) -> list:
    """Verified collectors online and pinged recently within `radius_km`."""
    profiles = CollectorProfile.objects.filter(
        is_online=True,
        is_verified=True,
        last_location_at__gte=CollectorProfile.stale_before(),
        user__is_active=True,
        **bounding_box(lat, lng, radius_km, "last_lat", "last_lng"),
    ).select_related("user")
    return [p.user for p in profiles if distance_km(lat, lng, p.last_lat, p.last_lng) <= radius_km]


def expire_stale_online() -> int:
    """Mark collectors offline after 10 minutes without a ping (contract 12.2)."""
    return (
        CollectorProfile.objects.filter(is_online=True)
        .exclude(last_location_at__gte=CollectorProfile.stale_before())
        .update(is_online=False, updated_at=timezone.now())
    )
