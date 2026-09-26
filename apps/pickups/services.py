"""Pickup state changes (contract 8.1). Each transition locks the pickup
row, so concurrent actions (two collectors accepting, a seller cancelling
while the collector sets off) resolve to exactly one winner. Pushes are
queued after commit."""

from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status

from apps.common.exceptions import ApiError
from apps.common.formatting import kg
from apps.common.geo import distance_km
from apps.notifications.push import notify, notify_many, text
from apps.wallet import services as wallet
from apps.wallet.models import WalletTransaction

from .messages import msg
from .models import (
    ACTIVE_STATUSES,
    COLLECTOR_WORKING_STATUSES,
    Dispute,
    Pickup,
    PickupDecline,
    PickupItem,
    PickupRating,
    PickupRefCounter,
    WeighFlag,
    WeighLine,
    WeighSheet,
)
from .presenters import sheet_totals, when_label
from .pricing import collector_earning, delivery_fee


def conflict(code: str, lang: str, key: str | None = None, data=None, **fmt) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, msg(key or code, lang, **fmt), data=data)


def not_found(lang: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", msg("pickup_not_found", lang))


def _locked(pickup_id) -> Pickup:
    return Pickup.objects.select_for_update().get(id=pickup_id)


def _next_ref() -> str:
    counter, _ = PickupRefCounter.objects.select_for_update().get_or_create(id=1)
    counter.last_value += 1
    counter.save(update_fields=["last_value"])
    return f"KB-{counter.last_value}"


# --- Booking -----------------------------------------------------------------


def book(seller, *, address, option, slot, lines, note, distance, lang) -> Pickup:
    """POST /pickups/ (contract 8.4). `slot` is None for self drop-off."""
    from .availability import slot_is_available

    total_kg = sum((line.approx_kg for line in lines), Decimal("0"))
    materials_total = sum(line.amount for line in lines)
    fee = delivery_fee(option, total_kg, distance)

    with transaction.atomic():
        # The counter row is the booking lock: refs and slot capacity are
        # decided one booking at a time.
        ref = _next_ref()
        active = Pickup.objects.filter(seller=seller, status__in=ACTIVE_STATUSES).count()
        if active >= settings.MAX_ACTIVE_PICKUPS:
            raise conflict("too_many_active_pickups", lang, limit=settings.MAX_ACTIVE_PICKUPS)
        if slot is not None and not slot_is_available(slot):
            raise conflict("slot_unavailable", lang)

        pickup = Pickup.objects.create(
            ref=ref,
            seller=seller,
            address=address,
            area=address.area,
            address_line=address.line,
            lat=address.lat,
            lng=address.lng,
            delivery_option=option,
            scheduled_date=timezone.localtime(slot.start).date() if slot else timezone.localdate(),
            slot_start=slot.start if slot else None,
            slot_end=slot.end if slot else None,
            note=note,
            approx_weight_kg=total_kg,
            estimated_total=materials_total,
            delivery_fee=fee,
            estimated_payout=max(materials_total - fee, 0),
            distance_km=Decimal(str(round(distance, 2))) if distance is not None else None,
            collector_earning=collector_earning(total_kg, fee),
        )
        PickupItem.objects.bulk_create(
            PickupItem(
                pickup=pickup, material_id=line.rate.id, approx_kg=line.approx_kg, price_per_kg=line.rate.price_per_kg
            )
            for line in lines
        )

    if option != Pickup.DeliveryOption.SELF_DROPOFF:
        _announce_new_job(pickup)
    return pickup


def _announce_new_job(pickup: Pickup) -> None:
    from apps.collectors.services import online_collectors_near

    collectors = online_collectors_near(pickup.lat, pickup.lng, settings.JOB_RADIUS_KM)
    notify_many(
        collectors,
        "new_job",
        {"pickup_id": str(pickup.id)},
        kg=str(kg(pickup.approx_weight_kg)),
        area=pickup.area,
        when=lambda lang: when_label(pickup, lang),
    )


def cancel(seller, pickup_id, reason: str, note: str, lang: str) -> Pickup:
    """POST /pickups/{id}/cancel/ (contract 8.7): only requested or matched."""
    with transaction.atomic():
        pickup = Pickup.objects.select_for_update().filter(id=pickup_id, seller=seller).first()
        if pickup is None:
            raise not_found(lang)
        if pickup.status not in (Pickup.Status.REQUESTED, Pickup.Status.MATCHED):
            raise conflict("cannot_cancel", lang)
        pickup.status = Pickup.Status.CANCELLED
        pickup.cancelled_at = timezone.now()
        pickup.cancel_reason = reason
        pickup.cancel_note = note
        pickup.save(update_fields=["status", "cancelled_at", "cancel_reason", "cancel_note", "updated_at"])

    if pickup.collector_id:
        notify(pickup.collector, "pickup_cancelled", {"pickup_id": str(pickup.id)}, ref=pickup.ref)
    return pickup


def expire_pickups(ids) -> int:
    """Move still-requested pickups past their slot to expired and tell sellers."""
    expired = []
    with transaction.atomic():
        now = timezone.now()
        for pickup in Pickup.objects.select_for_update().filter(
            id__in=ids, status=Pickup.Status.REQUESTED, slot_end__lt=now
        ):
            pickup.status = Pickup.Status.EXPIRED
            pickup.expired_at = now
            pickup.save(update_fields=["status", "expired_at", "updated_at"])
            expired.append(pickup)
    for pickup in expired:
        notify(pickup.seller, "pickup_expired", {"pickup_id": str(pickup.id)}, ref=pickup.ref)
    return len(expired)


def rate(user, pickup_id, stars: int, comment: str, lang: str) -> PickupRating:
    """POST /pickups/{id}/rating/ (contract 8.8): each side once."""
    pickup = Pickup.objects.filter(id=pickup_id).select_related("seller", "collector").first()
    if pickup is None or user.id not in (pickup.seller_id, pickup.collector_id):
        raise not_found(lang)
    if pickup.status != Pickup.Status.COMPLETED or pickup.collector_id is None:
        raise conflict("pickup_not_completed", lang)
    ratee = pickup.collector if user.id == pickup.seller_id else pickup.seller
    try:
        with transaction.atomic():
            return PickupRating.objects.create(pickup=pickup, rater=user, ratee=ratee, stars=stars, comment=comment)
    except IntegrityError:
        raise conflict("already_rated", lang) from None


# --- Collector side ----------------------------------------------------------


def collector_busy(collector) -> bool:
    """Has a job accepted and not finished (one at a time in v2)."""
    return (
        Pickup.objects.filter(collector=collector, status__in=COLLECTOR_WORKING_STATUSES).exists()
        or Pickup.objects.filter(
            collector=collector,
            status=Pickup.Status.DISPUTED,
            weigh_sheet__status__in=[WeighSheet.Status.LIVE, WeighSheet.Status.SUBMITTED],
        ).exists()
    )


def accept_job(collector, profile, pickup_id, lang: str) -> Pickup:
    """POST /collector/jobs/{id}/accept/ (contract 12.5): first accept wins."""
    if not profile.is_verified:
        raise ApiError(status.HTTP_403_FORBIDDEN, "collector_not_verified", msg("collector_not_verified", lang))
    with transaction.atomic():
        pickup = Pickup.objects.select_for_update().filter(id=pickup_id).first()
        if pickup is None:
            raise not_found(lang)
        if pickup.collector_id == collector.id and pickup.status != Pickup.Status.REQUESTED:
            return pickup  # repeat of this collector's own accept
        if pickup.status != Pickup.Status.REQUESTED or pickup.collector_id is not None:
            raise conflict("job_taken", lang)
        if pickup.delivery_option == Pickup.DeliveryOption.SELF_DROPOFF:
            raise not_found(lang)
        if not profile.effectively_online:
            raise conflict("collector_offline", lang)
        if collector_busy(collector):
            raise conflict("has_active_job", lang)
        pickup.collector = collector
        pickup.status = Pickup.Status.MATCHED
        pickup.matched_at = timezone.now()
        pickup.save(update_fields=["collector", "status", "matched_at", "updated_at"])

    notify(
        pickup.seller,
        "collector_matched",
        {"pickup_id": str(pickup.id)},
        name=collector.display_first_name or collector.full_name or "",
        ref=pickup.ref,
        when=lambda lang_: when_label(pickup, lang_),
    )
    return pickup


def decline_job(collector, pickup_id, reason: str, lang: str) -> None:
    pickup = Pickup.objects.filter(id=pickup_id, status=Pickup.Status.REQUESTED).first()
    if pickup is None:
        raise not_found(lang)
    PickupDecline.objects.get_or_create(pickup=pickup, collector=collector, defaults={"reason": reason})


TRANSITIONS = {
    Pickup.Status.ON_THE_WAY: (Pickup.Status.MATCHED, "on_the_way_at"),
    Pickup.Status.ARRIVED: (Pickup.Status.ON_THE_WAY, "arrived_at"),
}


def advance(collector, pickup_id, new_status: str, lang: str) -> Pickup:
    """POST /collector/pickups/{id}/status/ (contract 12.7)."""
    with transaction.atomic():
        pickup = Pickup.objects.select_for_update().filter(id=pickup_id, collector=collector).first()
        if pickup is None:
            raise not_found(lang)
        required, stamp = TRANSITIONS[new_status]
        if pickup.status != required:
            raise conflict("invalid_transition", lang)
        pickup.status = new_status
        setattr(pickup, stamp, timezone.now())
        pickup.save(update_fields=["status", stamp, "updated_at"])

    name = collector.display_first_name or collector.full_name or ""
    if new_status == Pickup.Status.ON_THE_WAY:
        eta = _eta(collector, pickup)
        notify(
            pickup.seller,
            "pickup_status",
            {"pickup_id": str(pickup.id), "status": new_status},
            title_key="pickup_status.on_the_way.title",
            body_key="pickup_status.on_the_way.body" if eta else "pickup_status.on_the_way.body_no_eta",
            name=name,
            eta=eta,
            ref=pickup.ref,
        )
    else:
        notify(
            pickup.seller,
            "pickup_status",
            {"pickup_id": str(pickup.id), "status": new_status},
            title_key="pickup_status.arrived.title",
            body_key="pickup_status.arrived.body",
            name=name,
        )
    return pickup


def _eta(collector, pickup) -> int | None:
    import math

    profile = getattr(collector, "collector_profile", None)
    if profile is None or not profile.has_location:
        return None
    km = distance_km(profile.last_lat, profile.last_lng, pickup.lat, pickup.lng)
    return max(1, math.ceil(km / settings.COLLECTOR_AVG_SPEED_KMH * 60))


def save_sheet(collector, pickup_id, lines: list[dict], lang: str):
    """PUT /collector/pickups/{id}/weigh-sheet/ (contract 12.9): replace all
    lines at today's server rates; the first save moves the pickup to weighing."""
    from apps.materials.services import rate_map

    rates = rate_map()
    missing = [line["material_id"] for line in lines if line["material_id"] not in rates]
    if missing:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "material_not_found",
            msg("material_not_found", lang),
            errors={"lines": [msg("material_not_found_item", lang, id=m) for m in missing]},
        )

    with transaction.atomic():
        pickup = Pickup.objects.select_for_update().filter(id=pickup_id, collector=collector).first()
        if pickup is None:
            raise not_found(lang)
        if pickup.status not in (Pickup.Status.ARRIVED, Pickup.Status.WEIGHING, Pickup.Status.DISPUTED):
            raise conflict("invalid_transition", lang)
        sheet, _ = WeighSheet.objects.get_or_create(pickup=pickup)
        if sheet.status != WeighSheet.Status.LIVE:
            raise conflict("sheet_closed", lang)

        sheet.lines.all().delete()
        WeighLine.objects.bulk_create(
            WeighLine(
                sheet=sheet,
                material_id=line["material_id"],
                rate_per_kg=rates[line["material_id"]].price_per_kg,
                kg=line["kg"],
                position=i,
            )
            for i, line in enumerate(lines)
        )
        sheet.version += 1
        sheet.save(update_fields=["version", "updated_at"])
        if pickup.status == Pickup.Status.ARRIVED:
            pickup.status = Pickup.Status.WEIGHING
            pickup.weighing_at = timezone.now()
            pickup.save(update_fields=["status", "weighing_at", "updated_at"])
    return pickup, sheet


def submit_sheet(collector, pickup_id, lang: str):
    """POST .../weigh-sheet/submit/ (contract 12.10): freeze the lines."""
    with transaction.atomic():
        pickup = Pickup.objects.select_for_update().filter(id=pickup_id, collector=collector).first()
        if pickup is None:
            raise not_found(lang)
        sheet = WeighSheet.objects.select_for_update().filter(pickup=pickup).first()
        if sheet is None or pickup.status not in (Pickup.Status.WEIGHING, Pickup.Status.DISPUTED):
            raise conflict("invalid_transition", lang)
        if sheet.status != WeighSheet.Status.LIVE:
            raise conflict("sheet_closed", lang)
        if not sheet.lines.exists():
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                msg("sheet_empty", lang),
                errors={"lines": [msg("sheet_empty", lang)]},
            )
        sheet.status = WeighSheet.Status.SUBMITTED
        sheet.submitted_at = timezone.now()
        sheet.save(update_fields=["status", "submitted_at", "updated_at"])

    notify(pickup.seller, "weigh_sheet_ready", {"pickup_id": str(pickup.id)}, ref=pickup.ref)
    return pickup, sheet


# --- Seller side of the weigh-in --------------------------------------------


def seller_sheet(seller, pickup_id, lang, lock=False):
    queryset = Pickup.objects.select_for_update() if lock else Pickup.objects
    pickup = queryset.filter(id=pickup_id, seller=seller).first()
    if pickup is None:
        raise not_found(lang)
    sheet_qs = WeighSheet.objects.select_for_update() if lock else WeighSheet.objects
    sheet = sheet_qs.filter(pickup=pickup).first()
    if sheet is None or pickup.status not in (
        Pickup.Status.WEIGHING,
        Pickup.Status.DISPUTED,
        Pickup.Status.COMPLETED,
    ):
        raise conflict("weigh_sheet_not_started", lang)
    return pickup, sheet


def flag_line(seller, pickup_id, data: dict, lang: str):
    """POST /pickups/{id}/weigh-sheet/flags/ (contract 9.2)."""
    with transaction.atomic():
        pickup, sheet = seller_sheet(seller, pickup_id, lang, lock=True)
        if sheet.status == WeighSheet.Status.ACCEPTED or pickup.status == Pickup.Status.COMPLETED:
            raise conflict("sheet_closed", lang)
        line = next((ln for ln in sheet.lines.select_related("material") if ln.line_id == data["line_id"]), None)
        if line is None:
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "validation_error",
                msg("line_not_found", lang),
                errors={"line_id": [msg("line_not_found", lang)]},
            )
        if WeighFlag.objects.filter(sheet=sheet, material_id=line.material_id, status=WeighFlag.Status.OPEN).exists():
            raise conflict("line_already_flagged", lang)

        dispute = Dispute.objects.create(
            pickup=pickup,
            opened_by=seller,
            type=Dispute.Type.WEIGHT_DISAGREEMENT,
            note=data.get("note", ""),
        )
        flag = WeighFlag.objects.create(
            sheet=sheet,
            material_id=line.material_id,
            reason=data["reason"],
            expected=data.get("expected", ""),
            note=data.get("note", ""),
            dispute=dispute,
        )
        if pickup.status != Pickup.Status.DISPUTED:
            pickup.status = Pickup.Status.DISPUTED
            pickup.disputed_at = timezone.now()
            pickup.save(update_fields=["status", "disputed_at", "updated_at"])

    if pickup.collector_id:
        notify(
            pickup.collector,
            "line_flagged",
            {"pickup_id": str(pickup.id), "line_id": line.line_id},
            material=line.material.name,
            ref=pickup.ref,
        )
    return flag, dispute


def accept_sheet(seller, pickup_id, version: int, payout_method: str, lang: str) -> dict:
    """POST /pickups/{id}/weigh-sheet/accept/ (contract 9.3)."""
    with transaction.atomic():
        pickup, sheet = seller_sheet(seller, pickup_id, lang, lock=True)
        if sheet.status in (WeighSheet.Status.ACCEPTED, WeighSheet.Status.DISPUTED):
            raise conflict("sheet_closed", lang)
        if sheet.status == WeighSheet.Status.LIVE:
            raise conflict("sheet_not_submitted", lang)
        if version != sheet.version:
            raise conflict("sheet_changed", lang, data={"version": sheet.version})

        lines = list(sheet.lines.all())
        total_kg, _total, _fee, payout = sheet_totals(pickup, lines)
        has_open_flags = sheet.flags.filter(status=WeighFlag.Status.OPEN).exists()

        sheet.accepted_at = timezone.now()
        pickup.payout_method = payout_method
        pickup.final_weight_kg = total_kg
        if has_open_flags:
            sheet.status = WeighSheet.Status.DISPUTED
            sheet.save(update_fields=["status", "accepted_at", "updated_at"])
            pickup.settlement_status = Pickup.Settlement.HELD
            pickup.held_payout = payout
            pickup.save(
                update_fields=["payout_method", "final_weight_kg", "settlement_status", "held_payout", "updated_at"]
            )
            txn = None
        else:
            sheet.status = WeighSheet.Status.ACCEPTED
            sheet.save(update_fields=["status", "accepted_at", "updated_at"])
            txn = _settle(pickup, payout)

    balance = wallet.get_wallet(seller).balance
    return {
        "pickup": {
            "id": str(pickup.id),
            "ref": pickup.ref,
            "status": pickup.status,
            "final_total": pickup.final_total,
        },
        "settlement": {
            "status": pickup.settlement_status,
            "amount": payout,
            "payout_method": payout_method,
            "transaction_id": str(txn.id) if txn else None,
        },
        "wallet": {"balance": balance},
    }


def _settle(pickup: Pickup, amount: int):
    """Complete the pickup and move the money (inside the caller's transaction)."""
    cash = pickup.payout_method == WalletTransaction.Method.CASH
    txn, _ = wallet.post(
        pickup.seller,
        type=WalletTransaction.Type.PICKUP,
        amount=amount,
        method=WalletTransaction.Method.CASH if cash else WalletTransaction.Method.WALLET,
        pickup=pickup,
        weight_kg=pickup.final_weight_kg,
    )
    # The collector's cut is credited when the seller takes a wallet payout
    # (contract 12.10); with cash the collector settles at the door.
    credited_collector = False
    if not cash and pickup.collector_id and pickup.collector_earning:
        wallet.post(
            pickup.collector,
            type=WalletTransaction.Type.JOB_EARNING,
            amount=pickup.collector_earning,
            method=WalletTransaction.Method.WALLET,
            pickup=pickup,
            weight_kg=pickup.final_weight_kg,
        )
        credited_collector = True

    pickup.status = Pickup.Status.COMPLETED
    pickup.completed_at = timezone.now()
    pickup.final_total = amount
    pickup.settlement_status = Pickup.Settlement.PAID
    pickup.held_payout = None
    pickup.save(
        update_fields=[
            "status",
            "completed_at",
            "final_total",
            "final_weight_kg",
            "payout_method",
            "settlement_status",
            "held_payout",
            "updated_at",
        ]
    )

    notify(pickup.seller, "payment_settled", {"pickup_id": str(pickup.id)}, amount=amount, ref=pickup.ref)
    if credited_collector:
        notify(
            pickup.collector,
            "payment_settled",
            {"pickup_id": str(pickup.id)},
            amount=pickup.collector_earning,
            ref=pickup.ref,
        )
    return txn


# --- Disputes ----------------------------------------------------------------


def open_dispute(user, pickup_id, type_: str, note: str, lang: str) -> Dispute:
    """POST /disputes/ (contract 13.1): participants only."""
    pickup = Pickup.objects.filter(id=pickup_id).first()
    if pickup is None or user.id not in (pickup.seller_id, pickup.collector_id):
        raise not_found(lang)
    return Dispute.objects.create(pickup=pickup, opened_by=user, type=type_, note=note)


def close_dispute(dispute: Dispute, *, resolved: bool, note: str = "", adjusted_amount: int | None = None) -> None:
    """Support closes a dispute (admin action). Held payouts are settled once
    no open dispute remains; a sheet that was never accepted goes back to the
    seller to accept."""
    new_status = Dispute.Status.RESOLVED if resolved else Dispute.Status.REJECTED
    flag_status = WeighFlag.Status.RESOLVED if resolved else WeighFlag.Status.REJECTED
    with transaction.atomic():
        dispute = Dispute.objects.select_for_update().get(id=dispute.id)
        if dispute.status != Dispute.Status.OPEN:
            return
        pickup = _locked(dispute.pickup_id)
        dispute.status = new_status
        dispute.resolution_note = note
        dispute.adjusted_amount = adjusted_amount
        dispute.resolved_at = timezone.now()
        dispute.save()
        WeighFlag.objects.filter(dispute=dispute, status=WeighFlag.Status.OPEN).update(status=flag_status)

        still_open = pickup.disputes.filter(status=Dispute.Status.OPEN).exists()
        if pickup.status == Pickup.Status.DISPUTED and not still_open:
            sheet = WeighSheet.objects.select_for_update().filter(pickup=pickup).first()
            if pickup.settlement_status == Pickup.Settlement.HELD:
                amount = adjusted_amount if adjusted_amount is not None else (pickup.held_payout or 0)
                if sheet:
                    sheet.status = WeighSheet.Status.ACCEPTED
                    sheet.save(update_fields=["status", "updated_at"])
                _settle(pickup, amount)
            else:
                pickup.status = Pickup.Status.WEIGHING
                pickup.save(update_fields=["status", "updated_at"])

    status_key = f"status.{new_status}"
    for user in (pickup.seller, pickup.collector):
        if user is not None:
            notify(
                user,
                "dispute_updated",
                {"dispute_id": str(dispute.id), "pickup_id": str(pickup.id)},
                title=lambda lang, t=dispute.type: msg(f"dispute_{t}", lang),
                ref=pickup.ref,
                status=lambda lang, k=status_key: text(k, lang),
            )
