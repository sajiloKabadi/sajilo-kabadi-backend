from django.conf import settings
from django.db import models
from django.utils import timezone


class Material(models.Model):
    """A scrap material. Ids are small fixed integers (contract 1.1) because
    the app, the weigh sheet and rate alerts all refer to them."""

    class Category(models.TextChoices):
        METAL = "metal", "Metal"
        PAPER_PLASTIC = "paper_plastic", "Paper & plastic"
        OTHER = "other", "Other"

    id = models.PositiveSmallIntegerField(primary_key=True)
    name_en = models.CharField(max_length=60)
    name_ne = models.CharField(max_length=60)
    abbr = models.CharField(max_length=8)
    category = models.CharField(max_length=20, choices=Category.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "materials_material"
        ordering = ["id"]

    def __str__(self):
        return self.name_en

    def name(self, lang: str) -> str:
        return self.name_ne if lang == "ne" and self.name_ne else self.name_en


class MaterialRate(models.Model):
    """The price for one material in one city from `effective_date` on.
    Add a new row to change a rate; history drives the trend arrows."""

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="rates")
    city = models.CharField(max_length=40, default=settings.DEFAULT_CITY)
    price_per_kg = models.PositiveIntegerField()
    effective_date = models.DateField(default=timezone.localdate)
    published_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "materials_rate"
        constraints = [
            models.UniqueConstraint(fields=["material", "city", "effective_date"], name="unique_rate_per_day"),
        ]
        indexes = [models.Index(fields=["material", "city", "-effective_date"], name="rate_lookup_idx")]

    def __str__(self):
        return f"{self.material} {self.price_per_kg}/kg ({self.city}, {self.effective_date})"
