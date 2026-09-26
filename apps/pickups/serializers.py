from decimal import Decimal

from rest_framework import serializers

from apps.wallet.models import WalletTransaction

from .models import Dispute, Pickup, PickupDecline, WeighFlag


class ItemSerializer(serializers.Serializer):
    material_id = serializers.IntegerField(min_value=1)
    approx_kg = serializers.DecimalField(
        max_digits=5, decimal_places=1, min_value=Decimal("1"), max_value=Decimal("2000")
    )


def _unique_materials(items, field="material_id"):
    ids = [item[field] for item in items]
    if len(ids) != len(set(ids)):
        raise serializers.ValidationError("Each material may appear only once.")
    return items


class QuoteSerializer(serializers.Serializer):
    """POST /pickups/quote/ (contract 8.3)."""

    address_id = serializers.UUIDField(required=False, allow_null=True)
    delivery_option = serializers.ChoiceField(choices=Pickup.DeliveryOption.values)
    items = serializers.ListField(child=ItemSerializer(), min_length=1, max_length=20)

    def validate_items(self, value):
        return _unique_materials(value)


class BookSerializer(QuoteSerializer):
    """POST /pickups/ (contract 8.4)."""

    address_id = serializers.UUIDField()
    slot_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=32)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")


class CancelSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=Pickup.CancelReason.values)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")


class RatingSerializer(serializers.Serializer):
    stars = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class FlagSerializer(serializers.Serializer):
    line_id = serializers.CharField(max_length=20)
    reason = serializers.ChoiceField(choices=WeighFlag.Reason.values)
    expected = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class AcceptSheetSerializer(serializers.Serializer):
    sheet_version = serializers.IntegerField(min_value=0)
    payout_method = serializers.ChoiceField(choices=[WalletTransaction.Method.WALLET, WalletTransaction.Method.CASH])


class DisputeCreateSerializer(serializers.Serializer):
    pickup_id = serializers.UUIDField()
    type = serializers.ChoiceField(
        choices=[
            Dispute.Type.MISSED_PICKUP,
            Dispute.Type.PAYMENT,
            Dispute.Type.BEHAVIOUR,
            Dispute.Type.OTHER,
        ]
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


# --- Collector ---------------------------------------------------------------


class DeclineSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=PickupDecline.Reason.values, required=False, allow_blank=True)


class CollectorStatusSerializer(serializers.Serializer):
    """PUT /collector/status/ (contract 12.2)."""

    is_online = serializers.BooleanField()
    lat = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)


class JobStatusSerializer(serializers.Serializer):
    """POST /collector/pickups/{id}/status/ (contract 12.7)."""

    status = serializers.ChoiceField(choices=[Pickup.Status.ON_THE_WAY, Pickup.Status.ARRIVED])
    lat = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    lng = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)


class LocationSerializer(serializers.Serializer):
    """POST /collector/location/ (contract 12.8)."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    heading = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=359)
    accuracy_m = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)


class WeighLineSerializer(serializers.Serializer):
    material_id = serializers.IntegerField(min_value=1)
    kg = serializers.DecimalField(max_digits=5, decimal_places=1, min_value=Decimal("0.1"), max_value=Decimal("2000"))


class WeighSheetSerializer(serializers.Serializer):
    """PUT /collector/pickups/{id}/weigh-sheet/ (contract 12.9)."""

    lines = serializers.ListField(child=WeighLineSerializer(), max_length=40)

    def validate_lines(self, value):
        return _unique_materials(value)
