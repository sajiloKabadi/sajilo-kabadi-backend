from django.contrib import admin, messages

from . import services
from .models import PayoutMethod, Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "balance", "updated_at"]
    search_fields = ["user__phone_number"]
    readonly_fields = ["user", "balance", "updated_at"]


@admin.register(PayoutMethod)
class PayoutMethodAdmin(admin.ModelAdmin):
    list_display = ["user", "bank_name", "account_name", "is_default", "verified", "is_removed"]
    list_filter = ["verified", "bank_code", "is_removed"]
    search_fields = ["user__phone_number", "account_name"]
    raw_id_fields = ["user"]
    actions = ["mark_verified"]

    @admin.action(description="Mark selected bank accounts as verified")
    def mark_verified(self, request, queryset):
        count = queryset.update(verified=True)
        self.message_user(request, f"{count} account(s) verified.")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    """Ledger rows are never edited by hand: use the actions."""

    list_display = ["created_at", "wallet", "type", "amount", "method", "status"]
    list_filter = ["type", "status", "method"]
    search_fields = ["wallet__user__phone_number", "pickup__ref"]
    list_select_related = ["wallet__user", "pickup"]
    readonly_fields = [f.name for f in WalletTransaction._meta.fields]
    actions = ["complete_withdrawals", "fail_withdrawals"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Withdrawal transferred: mark completed")
    def complete_withdrawals(self, request, queryset):
        self._settle(request, queryset, True)

    @admin.action(description="Withdrawal failed: return money to the wallet")
    def fail_withdrawals(self, request, queryset):
        self._settle(request, queryset, False)

    def _settle(self, request, queryset, succeeded):
        pending = queryset.filter(type=WalletTransaction.Type.WITHDRAWAL, status=WalletTransaction.Status.PENDING)
        count = 0
        for txn in pending.select_related("payout_method", "wallet__user"):
            services.settle_withdrawal(txn, succeeded)
            count += 1
        self.message_user(request, f"{count} withdrawal(s) updated.", messages.SUCCESS)
