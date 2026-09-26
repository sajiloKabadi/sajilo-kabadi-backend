import datetime as dt

from django.conf import settings
from django.db import models
from django.utils import timezone


class CollectorProfile(models.Model):
    """A collector's approval, online state and last known position.
    An admin sets `is_verified` after checking vehicle and ID (contract 12)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="collector_profile"
    )
    is_verified = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    vehicle_number = models.CharField(max_length=30, blank=True)
    last_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_heading = models.PositiveSmallIntegerField(null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "collectors_profile"
        indexes = [
            models.Index(fields=["is_online", "is_verified", "last_lat", "last_lng"], name="collector_online_geo_idx")
        ]

    def __str__(self):
        return f"Collector {self.user}"

    @staticmethod
    def stale_before() -> dt.datetime:
        return timezone.now() - dt.timedelta(seconds=settings.COLLECTOR_OFFLINE_AFTER_SECONDS)

    @property
    def effectively_online(self) -> bool:
        """Online and pinged recently; no ping for 10 minutes means offline."""
        return bool(self.is_online and self.last_location_at and self.last_location_at >= self.stale_before())

    @property
    def has_location(self) -> bool:
        return self.last_lat is not None and self.last_lng is not None


class LocationPing(models.Model):
    """Raw location history; only the last 24 h is kept (housekeeping)."""

    collector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location_pings")
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    heading = models.PositiveSmallIntegerField(null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "collectors_location_ping"
        indexes = [models.Index(fields=["collector", "-recorded_at"], name="ping_collector_idx")]

    def __str__(self):
        return f"{self.collector_id} @ {self.lat},{self.lng} ({self.recorded_at})"


def profile_for(user) -> CollectorProfile:
    profile, _ = CollectorProfile.objects.get_or_create(user=user)
    return profile
