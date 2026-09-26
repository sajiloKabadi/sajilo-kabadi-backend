"""Distance helpers. Queries first narrow rows with an indexed bounding box,
then check the exact great-circle distance in Python, so "within 5 km"
never scans the whole table."""

import math

from django.conf import settings

EARTH_RADIUS_KM = 6371.0088


def distance_km(lat1, lng1, lat2, lng2) -> float:
    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat, lng, radius_km: float, lat_field: str = "lat", lng_field: str = "lng") -> dict:
    """ORM kwargs `<lat_field>__range` / `<lng_field>__range` for a square around a point."""
    lat, lng = float(lat), float(lng)
    dlat = radius_km / 111.32
    dlng = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return {
        f"{lat_field}__range": (lat - dlat, lat + dlat),
        f"{lng_field}__range": (lng - dlng, lng + dlng),
    }


def in_service_area(lat, lng) -> bool:
    """Kathmandu valley, as a configurable box (SERVICE_AREA_BBOX)."""
    min_lat, min_lng, max_lat, max_lng = settings.SERVICE_AREA_BBOX
    return min_lat <= float(lat) <= max_lat and min_lng <= float(lng) <= max_lng


def round_km(value: float) -> float:
    return round(value, 1)
