from django.contrib import admin

from .models import CollectorProfile, LocationPing


@admin.register(CollectorProfile)
class CollectorProfileAdmin(admin.ModelAdmin):
    """Approve collectors here after checking vehicle and ID (contract 12)."""

    list_display = ["user", "vehicle_number", "is_verified", "is_online", "last_location_at"]
    list_filter = ["is_verified", "is_online"]
    search_fields = ["user__phone_number", "user__full_name", "vehicle_number"]
    raw_id_fields = ["user"]
    readonly_fields = ["last_lat", "last_lng", "last_heading", "last_location_at", "updated_at"]
    actions = ["verify", "unverify"]

    @admin.action(description="Approve selected collectors")
    def verify(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_verified=True)} collector(s) approved.")

    @admin.action(description="Revoke approval (also sets offline)")
    def unverify(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_verified=False, is_online=False)} collector(s) revoked.")


@admin.register(LocationPing)
class LocationPingAdmin(admin.ModelAdmin):
    list_display = ["collector", "lat", "lng", "heading", "recorded_at"]
    search_fields = ["collector__phone_number"]
    list_select_related = ["collector"]
    date_hierarchy = "recorded_at"
