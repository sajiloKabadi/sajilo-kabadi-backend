from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Address(BaseModel):
    """A seller's saved pickup address (contract 7). Pickups copy the parts
    they need at booking, so editing or deleting an address never rewrites
    history."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=30, blank=True)
    area = models.CharField(max_length=80)
    line = models.CharField(max_length=255)
    city = models.CharField(max_length=60)
    ward = models.PositiveSmallIntegerField()
    landmark = models.CharField(max_length=120, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "sellers_address"
        ordering = ["-is_default", "created_at"]
        indexes = [models.Index(fields=["user", "-is_default", "created_at"], name="address_user_idx")]

    def __str__(self):
        return f"{self.label or self.area} ({self.user})"

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "label": self.label or None,
            "area": self.area,
            "line": self.line,
            "city": self.city,
            "ward": self.ward,
            "landmark": self.landmark or None,
            "lat": float(self.lat),
            "lng": float(self.lng),
            "is_default": self.is_default,
        }


def default_address(user) -> Address | None:
    return Address.objects.filter(user=user).order_by("-is_default", "created_at").first()
