from django.db import models

from apps.common.models import BaseModel


class DropoffCenter(BaseModel):
    """A kabadi center sellers can take scrap to (contract 10)."""

    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    phone = models.CharField(max_length=20, blank=True)
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    # Material categories accepted: metal / paper_plastic / other.
    accepts = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "dropoff_center"
        indexes = [models.Index(fields=["is_active", "lat", "lng"], name="dropoff_geo_idx")]

    def __str__(self):
        return self.name

    def is_open_at(self, moment) -> bool:
        return self.opens_at <= moment < self.closes_at
