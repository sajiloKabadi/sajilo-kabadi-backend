from django.contrib import admin

from .models import NotificationPreference


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "pickup_updates", "rate_alerts_enabled", "promotions", "updated_at"]
    list_filter = ["pickup_updates", "rate_alerts_enabled"]
    search_fields = ["user__phone_number"]
    raw_id_fields = ["user"]
