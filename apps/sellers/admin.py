from django.contrib import admin

from .models import Address


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["user", "label", "area", "city", "ward", "is_default", "created_at"]
    list_filter = ["city", "is_default"]
    search_fields = ["user__phone_number", "area", "line"]
    raw_id_fields = ["user"]
