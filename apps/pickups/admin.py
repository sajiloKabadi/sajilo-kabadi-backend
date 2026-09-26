from django.contrib import admin, messages

from . import services
from .models import Dispute, Pickup, PickupItem, PickupRating, WeighFlag, WeighLine, WeighSheet


class PickupItemInline(admin.TabularInline):
    model = PickupItem
    extra = 0
    readonly_fields = ["material", "approx_kg", "price_per_kg"]
    can_delete = False


@admin.register(Pickup)
class PickupAdmin(admin.ModelAdmin):
    list_display = [
        "ref",
        "status",
        "seller",
        "collector",
        "delivery_option",
        "slot_start",
        "final_total",
        "created_at",
    ]
    list_filter = ["status", "delivery_option", "settlement_status"]
    search_fields = ["ref", "seller__phone_number", "collector__phone_number", "area"]
    list_select_related = ["seller", "collector"]
    raw_id_fields = ["seller", "collector", "address"]
    date_hierarchy = "created_at"
    inlines = [PickupItemInline]
    readonly_fields = ["ref", "created_at", "updated_at"]


class WeighLineInline(admin.TabularInline):
    model = WeighLine
    extra = 0
    readonly_fields = ["material", "rate_per_kg", "kg"]
    can_delete = False


@admin.register(WeighSheet)
class WeighSheetAdmin(admin.ModelAdmin):
    list_display = ["pickup", "status", "version", "submitted_at", "accepted_at"]
    list_filter = ["status"]
    search_fields = ["pickup__ref"]
    inlines = [WeighLineInline]
    readonly_fields = ["pickup", "version", "submitted_at", "accepted_at"]


@admin.register(WeighFlag)
class WeighFlagAdmin(admin.ModelAdmin):
    list_display = ["sheet", "material", "reason", "expected", "status", "created_at"]
    list_filter = ["status", "reason"]
    search_fields = ["sheet__pickup__ref"]


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    """Fill in resolution note (and adjusted amount to change the payout),
    save, then use an action to close the dispute. Closing settles any held
    payout and notifies both sides."""

    list_display = ["pickup", "type", "status", "opened_by", "adjusted_amount", "created_at"]
    list_filter = ["status", "type"]
    search_fields = ["pickup__ref", "opened_by__phone_number", "note"]
    list_select_related = ["pickup", "opened_by"]
    raw_id_fields = ["pickup", "opened_by"]
    readonly_fields = ["status", "resolved_at", "created_at"]
    actions = ["resolve", "reject"]

    @admin.action(description="Resolve (settle held payout; uses adjusted amount if set)")
    def resolve(self, request, queryset):
        self._close(request, queryset, True)

    @admin.action(description="Reject (settle held payout at the sheet amount)")
    def reject(self, request, queryset):
        self._close(request, queryset, False)

    def _close(self, request, queryset, resolved):
        count = 0
        for dispute in queryset.filter(status=Dispute.Status.OPEN):
            services.close_dispute(
                dispute,
                resolved=resolved,
                note=dispute.resolution_note,
                adjusted_amount=dispute.adjusted_amount if resolved else None,
            )
            count += 1
        self.message_user(request, f"{count} dispute(s) closed.", messages.SUCCESS)


@admin.register(PickupRating)
class PickupRatingAdmin(admin.ModelAdmin):
    list_display = ["pickup", "rater", "ratee", "stars", "created_at"]
    list_select_related = ["pickup", "rater", "ratee"]
