from django.contrib import admin

from .models import DropoffCenter


@admin.register(DropoffCenter)
class DropoffCenterAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "phone", "opens_at", "closes_at", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "address"]
