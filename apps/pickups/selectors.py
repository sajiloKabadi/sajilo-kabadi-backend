"""Read-side queries used by other apps (dashboard, profile, wallet)."""

import datetime as dt

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import ACTIVE_STATUSES, UPCOMING_STATUSES, Dispute, Pickup


def base_queryset():
    return Pickup.objects.select_related("seller", "collector", "collector__collector_profile", "weigh_sheet")


def expire_overdue(**filters) -> int:
    """Requested pickups nobody accepted before their slot ended become
    `expired` (contract 8.1). Run lazily on reads and by `housekeeping`."""
    from .services import expire_pickups

    overdue = Pickup.objects.filter(status=Pickup.Status.REQUESTED, slot_end__lt=timezone.now(), **filters)
    ids = list(overdue.values_list("id", flat=True)[:500])
    return expire_pickups(ids) if ids else 0


def next_pickup(user, lang: str, request=None) -> dict | None:
    """Home card: soonest pickup from requested to weighing (contract 5.1)."""
    from .presenters import summary_dict

    expire_overdue(seller=user)
    pickup = (
        base_queryset()
        .filter(seller=user, status__in=UPCOMING_STATUSES)
        .annotate(item_count=Count("items"))
        .order_by("scheduled_date", "slot_start", "created_at")
        .first()
    )
    return summary_dict(pickup, lang, request) if pickup else None


def address_has_active_pickup(address) -> bool:
    return Pickup.objects.filter(address=address, status__in=ACTIVE_STATUSES).exists()


def _completed(user):
    field = "collector" if user.is_collector else "seller"
    return Pickup.objects.filter(**{field: user}, status=Pickup.Status.COMPLETED)


def completed_count(user) -> int:
    """Completed pickups (seller) or jobs (collector)."""
    return _completed(user).count()


def completed_today(user) -> int:
    start = timezone.make_aware(dt.datetime.combine(timezone.localdate(), dt.time.min))
    return _completed(user).filter(completed_at__gte=start).count()


def held_amount(user) -> int:
    """Payouts waiting on open disputes (wallet held_amount, contract 11.1)."""
    total = Pickup.objects.filter(seller=user, settlement_status=Pickup.Settlement.HELD).aggregate(
        total=Sum("held_payout")
    )["total"]
    return total or 0


def user_stats(user) -> dict:
    """GET /me/ stats (contract 4.1)."""
    from .presenters import ratings_for

    rating, count = ratings_for([user.id]).get(user.id, (None, 0))
    recycled = _completed(user).aggregate(total=Sum("final_weight_kg"))["total"] or 0
    from apps.common.formatting import kg

    return {
        "rating": rating,
        "rating_count": count,
        "recycled_kg": kg(recycled) or 0,
        "pickups_done": completed_count(user),
    }


def open_dispute_titles(user, lang: str) -> list[str]:
    from .messages import msg

    types = (
        Dispute.objects.filter(Q(pickup__seller=user) | Q(pickup__collector=user) | Q(opened_by=user))
        .filter(status=Dispute.Status.OPEN)
        .values_list("type", flat=True)
        .distinct()
    )
    return [msg(f"dispute_{t}", lang) for t in types]
