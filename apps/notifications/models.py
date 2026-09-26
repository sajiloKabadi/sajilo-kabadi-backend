from django.conf import settings
from django.db import models


class NotificationPreference(models.Model):
    """GET/PATCH /me/notification-settings/ (contract 4.5). A missing row
    means the defaults below."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="notification_preference"
    )
    pickup_updates = models.BooleanField(default=True)
    rate_alerts_enabled = models.BooleanField(default=False)
    rate_alert_material_ids = models.JSONField(default=list, blank=True)
    promotions = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_preference"

    def __str__(self):
        return f"Notification settings of {self.user_id}"

    def as_dict(self) -> dict:
        return {
            "pickup_updates": self.pickup_updates,
            "rate_alerts": {"enabled": self.rate_alerts_enabled, "material_ids": list(self.rate_alert_material_ids)},
            "promotions": self.promotions,
        }


def preference_for(user) -> NotificationPreference:
    pref = NotificationPreference.objects.filter(user=user).first()
    return pref or NotificationPreference(user=user)
