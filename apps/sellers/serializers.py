from decimal import Decimal

from rest_framework import serializers


class AddressSerializer(serializers.Serializer):
    """POST /me/addresses/ and PATCH /me/addresses/{id}/ (contract 7)."""

    label = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)
    area = serializers.CharField(max_length=80)
    line = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=60)
    ward = serializers.IntegerField(min_value=1, max_value=35)
    landmark = serializers.CharField(max_length=120, required=False, allow_blank=True, allow_null=True)
    lat = serializers.DecimalField(max_digits=12, decimal_places=8, min_value=Decimal("-90"), max_value=Decimal("90"))
    lng = serializers.DecimalField(max_digits=12, decimal_places=8, min_value=Decimal("-180"), max_value=Decimal("180"))
    is_default = serializers.BooleanField(required=False)

    def validate(self, attrs):
        for field in ("label", "landmark"):
            if field in attrs:
                attrs[field] = (attrs[field] or "").strip()
        for field in ("lat", "lng"):
            if field in attrs:
                attrs[field] = attrs[field].quantize(Decimal("0.000001"))
        return attrs
