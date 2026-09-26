from rest_framework import serializers

from apps.materials.models import Material


class RateAlertsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    material_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=50)

    def validate_material_ids(self, value):
        ids = list(dict.fromkeys(value))
        known = set(Material.objects.filter(id__in=ids, is_active=True).values_list("id", flat=True))
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise serializers.ValidationError(f"Unknown material ids: {', '.join(map(str, unknown))}")
        return ids


class NotificationSettingsSerializer(serializers.Serializer):
    """PATCH /me/notification-settings/ with any subset of the object."""

    pickup_updates = serializers.BooleanField(required=False)
    rate_alerts = RateAlertsSerializer(required=False)
    promotions = serializers.BooleanField(required=False)
