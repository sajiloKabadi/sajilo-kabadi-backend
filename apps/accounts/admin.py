from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import OTPRequest, User, UserDevice


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-created_at"]
    list_display = ["phone_number", "full_name", "role", "language", "is_phone_verified", "is_active"]
    list_filter = ["role", "is_active", "language"]
    search_fields = ["phone_number", "full_name", "email"]
    fieldsets = (
        (None, {"fields": ("country_code", "phone_number", "password")}),
        ("Profile", {"fields": ("full_name", "email", "avatar", "role", "language", "is_phone_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone_number", "role")}),)


@admin.register(OTPRequest)
class OTPRequestAdmin(admin.ModelAdmin):
    list_display = [
        "phone_number",
        "role",
        "purpose",
        "created_at",
        "expires_at",
        "consumed_at",
        "invalidated_at",
        "locked_at",
        "attempt_count",
    ]
    list_filter = ["purpose", "role"]
    search_fields = ["phone_number"]
    exclude = ["code_hash"]
    readonly_fields = [f.name for f in OTPRequest._meta.fields if f.name != "code_hash"]


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "device_id", "app_version", "last_seen_at"]
    list_filter = ["platform"]
    search_fields = ["user__phone_number", "device_id"]
