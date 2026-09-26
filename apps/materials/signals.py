from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Material, MaterialRate
from .services import invalidate_board

RATE_ALERT_THRESHOLD_PERCENT = 5


@receiver(post_save, sender=MaterialRate)
def rate_saved(sender, instance: MaterialRate, created: bool, **kwargs):
    invalidate_board()
    previous = (
        MaterialRate.objects.filter(
            material_id=instance.material_id, city=instance.city, effective_date__lt=instance.effective_date
        )
        .order_by("-effective_date")
        .values_list("price_per_kg", flat=True)
        .first()
    )
    if not created or not previous:
        return
    change = (instance.price_per_kg - previous) * 100 / previous
    if abs(change) >= RATE_ALERT_THRESHOLD_PERCENT:
        from apps.notifications.push import send_rate_alerts

        transaction.on_commit(lambda: send_rate_alerts(instance.material, instance.price_per_kg, change))


@receiver(post_delete, sender=MaterialRate)
@receiver(post_save, sender=Material)
@receiver(post_delete, sender=Material)
def catalogue_changed(sender, **kwargs):
    invalidate_board()
