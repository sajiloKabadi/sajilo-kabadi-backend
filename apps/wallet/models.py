from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Wallet(models.Model):
    """One per user. `balance` is a cache of the ledger sum (contract 14):
    only apps.wallet.services changes it, under a row lock."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name="wallet"
    )
    balance = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "wallet_wallet"

    def __str__(self):
        return f"{self.user} Rs {self.balance}"


class PayoutMethod(BaseModel):
    """A bank account for withdrawals (contract 11.3). The full number is
    stored for transfers but never returned by the API."""

    class Type(models.TextChoices):
        BANK = "bank", "Bank"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payout_methods")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.BANK)
    bank_code = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=80)
    account_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=30)
    is_default = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    is_removed = models.BooleanField(default=False)

    class Meta:
        db_table = "wallet_payout_method"
        ordering = ["-is_default", "created_at"]

    def __str__(self):
        return self.label

    @property
    def label(self) -> str:
        return f"{self.bank_name} ••••{self.account_number[-4:]}"

    def as_dict(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.type,
            "bank_name": self.bank_name,
            "label": self.label,
            "is_default": self.is_default,
            "verified": self.verified,
        }


class WalletTransaction(BaseModel):
    """A ledger row. Signed amount: credits positive, debits negative."""

    class Type(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        DROPOFF = "dropoff", "Drop-off"
        JOB_EARNING = "job_earning", "Job earning"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Method(models.TextChoices):
        WALLET = "wallet", "Wallet"
        CASH = "cash", "Cash"
        BANK = "bank", "Bank"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="transactions")
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.IntegerField()
    method = models.CharField(max_length=10, choices=Method.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    # Cash pickups are listed for the record but never touch the balance.
    affects_balance = models.BooleanField(default=True)
    pickup = models.ForeignKey(
        "pickups.Pickup", on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    payout_method = models.ForeignKey(
        PayoutMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions"
    )
    weight_kg = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "wallet_transaction"
        indexes = [
            models.Index(fields=["wallet", "-created_at"], name="txn_wallet_recent_idx"),
            models.Index(fields=["wallet", "type", "status", "created_at"], name="txn_wallet_type_idx"),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} ({self.status})"
