"""The only code that moves money. Every change locks the wallet row, writes
a ledger row and re-derives the cached balance in the same transaction."""

import datetime as dt

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.common.formatting import bs_day_month, fiscal_year, iso, kg

from .messages import msg
from .models import PayoutMethod, Wallet, WalletTransaction

EARNING_TYPES = (
    WalletTransaction.Type.PICKUP,
    WalletTransaction.Type.DROPOFF,
    WalletTransaction.Type.JOB_EARNING,
)

# Pending withdrawals are already debited; failed ones are not.
BALANCE_FILTER = Q(affects_balance=True) & ~Q(status=WalletTransaction.Status.FAILED)


def get_wallet(user) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def _locked_wallet(user) -> Wallet:
    get_wallet(user)
    return Wallet.objects.select_for_update().get(user=user)


def _refresh_balance(wallet: Wallet) -> None:
    total = wallet.transactions.filter(BALANCE_FILTER).aggregate(total=Sum("amount"))["total"] or 0
    wallet.balance = total
    wallet.save(update_fields=["balance", "updated_at"])


def post(user, *, type, amount: int, method, status=WalletTransaction.Status.COMPLETED, **fields):
    """Write one ledger row and update the cached balance atomically."""
    with transaction.atomic():
        wallet = _locked_wallet(user)
        txn = WalletTransaction.objects.create(
            wallet=wallet,
            type=type,
            amount=amount,
            method=method,
            status=status,
            affects_balance=method != WalletTransaction.Method.CASH,
            completed_at=timezone.now() if status == WalletTransaction.Status.COMPLETED else None,
            **fields,
        )
        _refresh_balance(wallet)
    return txn, wallet


def withdraw(user, amount: int, payout_method: PayoutMethod):
    """Debit at once and create a pending withdrawal (contract 11.4).
    Returns (txn, wallet) or raises InsufficientBalance."""
    with transaction.atomic():
        wallet = _locked_wallet(user)
        if amount > wallet.balance:
            raise InsufficientBalance()
        txn = WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.WITHDRAWAL,
            amount=-amount,
            method=WalletTransaction.Method.BANK,
            status=WalletTransaction.Status.PENDING,
            payout_method=payout_method,
        )
        _refresh_balance(wallet)
    return txn, wallet


def settle_withdrawal(txn: WalletTransaction, succeeded: bool) -> None:
    """Called by support once the bank transfer completes or fails."""
    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(pk=txn.wallet_id)
        txn.refresh_from_db()
        if txn.status != WalletTransaction.Status.PENDING:
            return
        txn.status = WalletTransaction.Status.COMPLETED if succeeded else WalletTransaction.Status.FAILED
        txn.completed_at = timezone.now()
        txn.save(update_fields=["status", "completed_at", "updated_at"])
        _refresh_balance(wallet)

    from apps.notifications.push import notify, text

    status_key = "status.completed" if succeeded else "status.failed"
    notify(
        wallet.user,
        "withdrawal_status",
        {"transaction_id": str(txn.id), "status": txn.status},
        status=lambda lang: text(status_key, lang),
        amount=abs(txn.amount),
        bank=txn.payout_method.bank_name if txn.payout_method else "",
    )


class InsufficientBalance(Exception):
    pass


def default_payout_method(user) -> PayoutMethod | None:
    return PayoutMethod.objects.filter(user=user, is_removed=False).order_by("-is_default", "created_at").first()


def can_withdraw(user, balance: int, method: PayoutMethod | None = None) -> bool:
    if settings.PAYOUTS_ON_HOLD or balance < settings.MIN_WITHDRAWAL:
        return False
    return PayoutMethod.objects.filter(user=user, is_removed=False, verified=True).exists()


def wallet_card(user) -> dict:
    """Home balance card (contract 5.1)."""
    wallet = get_wallet(user)
    return {"balance": wallet.balance, "currency": "NPR", "can_withdraw": can_withdraw(user, wallet.balance)}


def summary(user) -> dict:
    """GET /wallet/ (contract 11.1)."""
    from apps.pickups.selectors import completed_count, held_amount

    wallet = get_wallet(user)
    year_label, year_start = fiscal_year()
    start = timezone.make_aware(dt.datetime.combine(year_start, dt.time.min))
    earned = (
        wallet.transactions.filter(
            type__in=EARNING_TYPES, status=WalletTransaction.Status.COMPLETED, amount__gt=0, created_at__gte=start
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    method = default_payout_method(user)
    return {
        "balance": wallet.balance,
        "currency": "NPR",
        "can_withdraw": can_withdraw(user, wallet.balance),
        "min_withdrawal": settings.MIN_WITHDRAWAL,
        "held_amount": held_amount(user),
        "earned_this_year": earned,
        "year_label": year_label,
        "pickups_done": completed_count(user),
        "default_payout_method": {"id": str(method.id), "label": method.label} if method else None,
    }


def title(txn: WalletTransaction, lang: str) -> str:
    if txn.type == WalletTransaction.Type.WITHDRAWAL:
        bank = txn.payout_method.bank_name if txn.payout_method else msg("bank", lang)
        return msg("title_withdrawal", lang, bank=bank)
    return msg(f"title_{txn.type}", lang)


def transaction_dict(txn: WalletTransaction, lang: str) -> dict:
    """Transaction history row (contract 11.2)."""
    created = timezone.localtime(txn.created_at)
    return {
        "id": str(txn.id),
        "type": txn.type,
        "title": title(txn, lang),
        "weight_kg": kg(txn.weight_kg),
        "amount": txn.amount,
        "method": txn.method,
        "method_label": msg(f"method_{txn.method}", lang),
        "pickup_ref": txn.pickup.ref if txn.pickup_id else None,
        "created_at": iso(txn.created_at),
        "date_label": bs_day_month(created.date(), lang),
        "status": txn.status,
    }
